"""Verify complete native captures against the frozen author-model fixture."""

from lib.errors import require

from pathlib import Path
import hashlib
import json
import re
import sys
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark/fixtures/unified-mysql-datasets"))
from verify_dataset import verify as frozen_verify

AUTHOR = ROOT / "benchmark/fixtures/author"
SALES = {"VENDA_CABECALHO", "VENDA_DETALHE", "VENDA_COMISSAO"}


def digest(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def counters(path):
    result = {}
    for line in Path(path).open(encoding="utf-8-sig"):
        if line.startswith("NEXT\t"):
            _, table, next_ = line.rstrip().split("\t")
            result[table] = int(next_)
    return result


def normalize(path, manifest, destination):
    """Normalize only native decimal display and permissible sales sequence advances."""
    with Path(path).open(encoding="utf-8-sig") as source, destination.open(
        "w", encoding="utf-8", newline="\n"
    ) as target:
        for raw in source:
            line = raw.rstrip("\r\n")
            if line.startswith("COLUMN\t"):
                kind, table, value = line.split("\t")
                value = json.loads(value)
                if table == "FPAS" and value[0] == "ALIQUOTA_SAT":
                    require(value[1] == "decimal(10,0)", "VERIFICATION_FAILED")
                    value[1] = "decimal"
                if table == "VENDA_COMISSAO" and value[0] == "VALOR_COMISSAO":
                    require(
                        value[1] == "decimal(18,6) unsigned zerofill",
                        "VERIFICATION_FAILED",
                    )
                    value[1] = "decimal(18,6)"
                line = (
                    kind
                    + "\t"
                    + table
                    + "\t"
                    + json.dumps(value, separators=(",", ":"))
                )
            if line.startswith("NEXT\t"):
                _, table, value = line.split("\t")
                expected = manifest["expected_auto_increment_next"][table]
                if table in SALES:
                    require(int(value) >= expected, "SALES_SEQUENCE_REGRESSION")
                    line = "NEXT\t" + table + "\t" + str(expected)
            if line.startswith("ROW\tVENDA_COMISSAO\t"):
                kind, table, value = line.split("\t")
                value = json.loads(value)
                if value[5] is not None:
                    require(
                        re.fullmatch("[0-9]{12}\\.[0-9]{6}", value[5]),
                        "ZEROFILL_DISPLAY",
                    )
                    value[5] = format(Decimal(value[5]), ".6f")
                line = (
                    kind
                    + "\t"
                    + table
                    + "\t"
                    + json.dumps(value, separators=(",", ":"))
                )
            target.write(line + "\n")


def verify_pair(manifest_path, before, after, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(Path(manifest_path).read_text())
    result = {}
    for label, path in [("before", before), ("after_content_schema_fk", after)]:
        if path is None:
            continue
        output = destination / (label + "-normalized.tsv")
        normalize(path, manifest, output)
        result[label] = frozen_verify(
            manifest_path,
            digest(manifest_path),
            AUTHOR / "model.xml",
            AUTHOR / "export-receipt.json",
            AUTHOR / "schema.sql",
            AUTHOR / "views.sql",
            output,
        )
        result[label]["raw_capture_sha256"] = digest(path)
    if after is not None:
        b, a = (counters(before), counters(after))
        require(a.keys() == b.keys(), "VERIFICATION_FAILED")
        changed = {t: {"before": b[t], "after": a[t]} for t in b if a[t] != b[t]}
        require(
            set(changed) <= SALES
            and all((v["after"] > v["before"] for v in changed.values())),
            "UNEXPECTED_SEQUENCE_CHANGE",
        )
        result["sequence_changes"] = changed
    result["normalization"] = (
        "Native DECIMAL(10,0) default spelling, commission ZEROFILL display and advancing sales auto-increment metadata only; raw content and schema retained."
    )
    (destination / "database-verification.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    return result
