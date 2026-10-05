from lib.errors import require
import json
import re
import collections
import sys
import hashlib
from decimal import Decimal
from pathlib import Path


def run(directory):
    P = Path(directory).resolve()
    A = P / "actual"
    pk = json.loads((P / "packet.json").read_text())
    run = pk["cells"][0]["run_id"]
    columns = {}
    baseline = {}
    final = {}
    allowed = {
        "VENDA_CABECALHO": set(range(1, 5)),
        "VENDA_DETALHE": {1, 6, 11, 16},
        "VENDA_COMISSAO": set(range(1, 5)),
    }
    for line in (A / "db-before.tsv").open(encoding="utf-8-sig"):
        if line.startswith("COLUMN\t"):
            _, t, j = line.rstrip().split("\t")
            columns.setdefault(t, []).append(json.loads(j)[0])

    def snapshot(path):
        rows = {}
        h = hashlib.sha256()
        for raw in path.open("rb"):
            f = raw.decode("utf-8-sig").rstrip("\r\n").split("\t", 2)
            if f[0] == "ROW":
                v = json.loads(f[2])
                key = (f[1], int(v[0]))
                if key[1] in allowed.get(key[0], set()):
                    rows[key] = v
                    continue
            if f[0] != "NEXT":
                h.update(raw)
        return (rows, h.hexdigest())

    baseline, untouched = snapshot(A / "db-before.tsv")
    require(len(baseline) == 12, "VERIFICATION_FAILED")
    expected = {k: dict(zip(columns[k[0]], v)) for k, v in baseline.items()}
    increments = collections.Counter()
    native_success = 0
    errors = collections.Counter()
    for w in range(32):
        for line in (A / (run + "-" + str(w) + ".ndjson")).open(encoding="utf-8-sig"):
            e = json.loads(line)
            require(
                e["identity"]["worker_id"] == w and e["identity"]["run_id"] == run,
                "VERIFICATION_FAILED",
            )
            if (
                e["event"] == "attempt_terminal"
                and e["outcome"] == "COMPLETED_PENDING_INDEPENDENT_OBSERVER"
            ):
                native_success += 1
            if e["event"] == "database_failure":
                require(
                    e["fields"]["mysql_errno"] in [1180, 3100, 3101, 1213, 1205],
                    "VERIFICATION_FAILED",
                )
                errors[e["fields"]["mysql_errno"]] += 1
            require(e["event"] != "native_error", "VERIFICATION_FAILED")

    def value_equal(encoded, value):
        if encoded == "NULL":
            return value is None
        if value is None:
            return False
        if encoded.startswith("'"):
            text = encoded[1:-1].replace("\\'", "'").replace("\\\\", "\\")
            if re.fullmatch("\\d{4}:\\d{2}:\\d{2}", text):
                text = text.replace(":", "-")
            return str(value) == text
        try:
            return Decimal(encoded) == Decimal(str(value))
        except Exception:
            return False

    pending = []
    row = None
    section = None
    transactions = 0
    for line in (A / "sale-row-events.txt").open(encoding="utf-8-sig"):
        line = line.rstrip("\r\n")
        m = re.match(
            "^### (INSERT INTO|UPDATE|DELETE FROM) `t2ti_bench`\\.`(\\w+)`", line, re.I
        )
        if m:
            row = {"op": m[1], "table": m[2].upper(), "before": {}, "after": {}}
            pending.append(row)
            section = None
        elif row and line == "### WHERE":
            section = "before"
        elif row and line == "### SET":
            section = "after"
        elif row and (m := re.match("^###\\s+@(\\d+)=(.*?) /\\*", line)):
            row[section][int(m[1])] = m[2]
        elif "Xid =" in line:
            if pending:
                require(
                    len(pending) == 3 and all((r["op"] == "UPDATE" for r in pending)),
                    "NON_ATOMIC_SHARED_UPDATE",
                )
                tables = {r["table"]: r for r in pending}
                require(set(tables) == set(allowed), "VERIFICATION_FAILED")
                hid = int(tables["VENDA_CABECALHO"]["before"][1])
                require(1 <= hid <= 4, "VERIFICATION_FAILED")
                did = 5 * (hid - 1) + 1
                keys = {
                    "VENDA_CABECALHO": hid,
                    "VENDA_DETALHE": did,
                    "VENDA_COMISSAO": hid,
                }
                for t, ident in keys.items():
                    r = tables[t]
                    require(
                        int(r["before"][1]) == ident and int(r["after"][1]) == ident,
                        "VERIFICATION_FAILED",
                    )
                    before = expected[t, ident]
                    require(len(r["before"]) == len(columns[t]), "VERIFICATION_FAILED")
                    require(
                        all(
                            (
                                value_equal(r["before"][i + 1], before[n])
                                for i, n in enumerate(columns[t])
                            )
                        ),
                        ("BEFORE_IMAGE", t, hid),
                    )
                h = expected["VENDA_CABECALHO", hid]
                d = expected["VENDA_DETALHE", did]
                c = expected["VENDA_COMISSAO", hid]
                qty = Decimal(str(d["QUANTIDADE"])) + 1
                delta = Decimal(str(d["VALOR_UNITARIO"]))
                comm_delta = delta * Decimal(str(d["TAXA_COMISSAO"])) / 100
                d.update(
                    QUANTIDADE=qty,
                    VALOR_SUBTOTAL=qty * delta,
                    VALOR_TOTAL=qty * delta,
                    VALOR_COMISSAO=qty * comm_delta,
                )
                h.update(
                    VALOR_SUBTOTAL=Decimal(str(h["VALOR_SUBTOTAL"])) + delta,
                    VALOR_TOTAL=Decimal(str(h["VALOR_TOTAL"])) + delta,
                    VALOR_COMISSAO=Decimal(str(h["VALOR_COMISSAO"])) + comm_delta,
                    OBSERVACAO="SYNTHETIC SHARED UPDATED",
                )
                c.update(
                    VALOR_VENDA=h["VALOR_TOTAL"], VALOR_COMISSAO=h["VALOR_COMISSAO"]
                )
                for t, ident in keys.items():
                    require(
                        all(
                            (
                                value_equal(
                                    tables[t]["after"][i + 1], expected[t, ident][n]
                                )
                                for i, n in enumerate(columns[t])
                            )
                        ),
                        ("AFTER_IMAGE", t, hid),
                    )
                increments[hid] += 1
                transactions += 1
            pending = []
            row = None
            section = None
    require(
        transactions == native_success and transactions > 0,
        ("NATIVE_COMMIT_COUNT", transactions, native_success),
    )
    replicas = {}
    for role in pk["database_roles"]:
        final, rest = snapshot(A / (role + "-after.tsv"))
        require(rest == untouched, (role, "NON_POOL_CONTENT_CHANGED"))
        require(final.keys() == baseline.keys(), "VERIFICATION_FAILED")
        for key, values in final.items():
            exp = expected[key]
            for n, v in zip(columns[key[0]], values):
                want = exp[n]
                if isinstance(want, Decimal):
                    require(Decimal(str(v)) == want, (key, n, v, want))
                else:
                    require(v == want, (key, n, v, want))
        replicas[role] = {"full_non_pool_sha256": rest, "pool_rows_verified": 12}
    result = {
        "status": "ATOMIC_SHARED_INCREMENT_COMMITS_NO_LOST_UPDATES_AND_ALL_REPLICA_CONTENT_VERIFIED",
        "run_id": run,
        "committed_updates_all_phases": transactions,
        "header_increments": dict(increments),
        "database_failures_all_phases": dict(errors),
        "replicas": replicas,
        "measured_operation_retries": 0,
    }
    (P / "contention-verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    run(sys.argv[1])
