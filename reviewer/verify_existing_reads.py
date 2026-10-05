from lib.errors import require
from pathlib import Path
import sys
import json
import collections
import decimal
import hashlib


def run(directory):
    P = Path(directory).resolve()
    A = P / "actual"
    report = json.loads((P / "results.json").read_text())
    checks = {}
    columns = collections.defaultdict(list)
    rows = {}
    types = {}
    for line in (A / "db-before.tsv").open(encoding="utf-8-sig"):
        if line.startswith("COLUMN\t"):
            _, t, v = line.rstrip().split("\t")
            v = json.loads(v)
            columns[t.upper()].append((v[0], v[1]))
        elif line.startswith("ROW\tVENDA_"):
            _, t, v = line.rstrip().split("\t")
            v = json.loads(v)
            if t in ["VENDA_CABECALHO", "VENDA_DETALHE", "VENDA_COMISSAO"]:
                rows[t, int(v[0])] = v
    for c in report["cells"]:
        if c["operation"] != "SALE_READ" or not c["execution_complete"]:
            continue
        checked = 0
        attempts = 0
        errors = collections.Counter()
        seen = set()
        for f in A.glob(c["run_id"] + "-*.ndjson"):
            for line in f.open(encoding="utf-8-sig"):
                e = json.loads(line)
                if e["event"] != "existing_original_vo_read":
                    continue
                key = e["global_attempt_id"]
                require(key not in seen, "VERIFICATION_FAILED")
                seen.add(key)
                attempts += 1
                fields = e["fields"]
                require(
                    set(fields)
                    == {"VENDA_CABECALHO", "VENDA_DETALHE", "VENDA_COMISSAO"},
                    "VERIFICATION_FAILED",
                )
                h = fields["VENDA_CABECALHO"]
                d = fields["VENDA_DETALHE"]
                co = fields["VENDA_COMISSAO"]
                require(len(h) == len(co) == 1 and len(d) == 5, "VERIFICATION_FAILED")
                hid = int(h[0]["ID"])
                require(
                    int(co[0]["ID_VENDA_CABECALHO"]) == hid
                    and all((int(r["ID_VENDA_CABECALHO"]) == hid for r in d)),
                    "VERIFICATION_FAILED",
                )
                for t, rr in fields.items():
                    for r in rr:
                        expected = rows[t, int(r["ID"])]
                        require(
                            set(r) <= {name for name, typ in columns[t]},
                            "VERIFICATION_FAILED",
                        )
                        require(
                            len(r)
                            == {
                                "VENDA_CABECALHO": 26,
                                "VENDA_DETALHE": 11,
                                "VENDA_COMISSAO": 8,
                            }[t],
                            "VERIFICATION_FAILED",
                        )
                        for index, (name, typ) in enumerate(columns[t]):
                            if name not in r:
                                continue
                            raw = expected[index]
                            actual = r[name]
                            typ = typ.lower()
                            if raw is None:
                                want = (
                                    "ORIGINAL_VO_DATE_ZERO"
                                    if typ.startswith(("date", "timestamp"))
                                    else (
                                        ""
                                        if typ.startswith(
                                            ("char", "varchar", "text", "blob")
                                        )
                                        else "0"
                                    )
                                )
                                equal = str(actual) == want
                            elif typ.startswith(
                                (
                                    "int",
                                    "smallint",
                                    "bigint",
                                    "tinyint",
                                    "decimal",
                                    "float",
                                    "double",
                                    "numeric",
                                )
                            ):
                                equal = decimal.Decimal(str(actual)) == decimal.Decimal(
                                    str(raw)
                                )
                            else:
                                equal = str(actual) == str(raw)
                            if not equal:
                                errors[t + "." + name] += 1
                        checked += 1
        good = not errors and checked == 7 * attempts and (attempts > 0)
        checks[c["run_id"]] = {
            "status": (
                "EXISTING_ORIGINAL_VO_DATASET_VALUES_VERIFIED" if good else "FAILED"
            ),
            "read_attempts_all_phases": attempts,
            "original_vo_rows_checked": checked,
            "errors": dict(errors),
        }
        c["independent_database_verification"] = checks[c["run_id"]]["status"]
        c["verified_business_goodput_per_second"] = (
            c["worker_reported_throughput_per_second"] if good else None
        )
        c["verified_concurrency_aligned_goodput_per_second"] = (
            c.get("concurrency_aligned", {}).get("worker_reported_operations_second")
            if good
            else None
        )
    (P / "existing-read-verification.json").write_text(
        json.dumps(
            {
                "capture_sha256": hashlib.file_digest(
                    (A / "db-before.tsv").open("rb"), "sha256"
                ).hexdigest(),
                "cells": checks,
            },
            indent=2,
        )
        + "\n"
    )
    (P / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(checks))
    require(
        checks
        and all(
            (
                c["status"] == "EXISTING_ORIGINAL_VO_DATASET_VALUES_VERIFIED"
                for c in checks.values()
            )
        ),
        "VERIFICATION_FAILED",
    )


if __name__ == "__main__":
    run(sys.argv[1])
