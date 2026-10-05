from lib.errors import require
from pathlib import Path
import json
import re
import collections
import hashlib
import sys
from decimal import Decimal


def run(directory):
    P = Path(directory).resolve()
    A = P / "actual"
    packet = json.loads((P / "packet.json").read_text())
    report = json.loads((P / "results.json").read_text())
    cells = [
        c
        for c in report["cells"]
        if c["execution_complete"] and c["operation"].startswith("SALE_")
    ]
    claims = {
        c["run_id"]: json.loads((P / (c["run_id"] + "-owned-ids.json")).read_text())
        for c in cells
    }
    owner = {
        (t, int(i)): c["run_id"]
        for c in cells
        for t, ids in claims[c["run_id"]].items()
        for i in ids
    }
    columns = collections.defaultdict(list)
    for line in (A / "db-before.tsv").open():
        if line.startswith("COLUMN\t"):
            _, t, v = line.rstrip().split("\t")
            v = json.loads(v)
            columns[t.upper()].append((v[0], v[1]))
    read_expected = {}
    read_seen = collections.Counter()
    conflict_counts = collections.Counter()
    success_counts = collections.Counter()
    success_headers = collections.defaultdict(set)
    atomic_deletes = collections.defaultdict(set)
    for c in cells:
        for file in A.glob(c["run_id"] + "-*.ndjson"):
            for line in file.open(encoding="utf-8-sig"):
                e = json.loads(line)
                if e["event"] == "certification_conflict":
                    require(
                        e["fields"]["mysql_errno"] == 3101
                        and e["fields"]["exception_class"] == "TDBXError",
                        "VERIFICATION_FAILED",
                    )
                    conflict_counts[c["run_id"]] += 1
                if (
                    e["event"] == "attempt_terminal"
                    and e["outcome"] == "COMPLETED_PENDING_INDEPENDENT_OBSERVER"
                ):
                    success_counts[c["run_id"]] += 1
                    hs = e["claimed_owned_ids_require_independent_observation"][
                        "VENDA_CABECALHO"
                    ]
                    require(
                        len(hs) == 1 and hs[0] not in success_headers[c["run_id"]],
                        "SUCCESS_ORDER_ID_REUSED",
                    )
                    success_headers[c["run_id"]].add(hs[0])
                    require(e["retries"] == 0, "VERIFICATION_FAILED")
                    if c["operation"] != "SALE_READ":
                        require("COMMIT" in e["business_steps"], "VERIFICATION_FAILED")
    for c in cells:
        if c["operation"] != "SALE_READ":
            continue
        for file in A.glob(c["run_id"] + "-*.ndjson"):
            for line in file.open(encoding="utf-8-sig"):
                e = json.loads(line)
                if e["event"] == "original_vo_read":
                    for table, rows in e["fields"].items():
                        for row in rows:
                            key = (table, int(row["ID"]))
                            require(
                                owner.get(key) == c["run_id"], "VERIFICATION_FAILED"
                            )
                            require(key not in read_expected, "VERIFICATION_FAILED")
                            read_expected[key] = row
                            read_seen[c["run_id"]] += 1
    stats = {
        k: {
            "insert": 0,
            "delete": 0,
            "update": 0,
            "insert_order": None,
            "delete_order": None,
        }
        for k in owner
    }
    errors = collections.defaultdict(collections.Counter)
    create_count = collections.Counter()
    update_count = collections.Counter()
    verified_reads = collections.Counter()

    def num(v):
        return Decimal(v.strip("'"))

    def projection_equal(db, row, table):
        if len(db) != len(columns[table]):
            return False
        for n, (name, typ) in enumerate(columns[table], 1):
            if name not in row:
                continue
            value = db[n]
            actual = row[name]
            typ = typ.lower()
            if value == "NULL":
                expected = (
                    "ORIGINAL_VO_DATE_ZERO"
                    if typ.startswith(("date", "timestamp"))
                    else (
                        ""
                        if typ.startswith(("char", "varchar", "text", "blob"))
                        else "0"
                    )
                )
                if str(actual) != expected:
                    return False
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
                if Decimal(str(actual)) != num(value):
                    return False
            else:
                if not (value.startswith("'") and value.endswith("'")):
                    return False
                expected = value[1:-1].replace("\\'", "'").replace("\\\\", "\\")
                if typ.startswith("date") and re.fullmatch(
                    "\\d{4}:\\d{2}:\\d{2}", expected
                ):
                    expected = expected.replace(":", "-")
                if str(actual) != expected:
                    return False
        return len(row) == {
            "VENDA_CABECALHO": 26,
            "VENDA_DETALHE": 11,
            "VENDA_COMISSAO": 8,
        }[table] and set(row) <= {name for name, typ in columns[table]}

    order = 0
    pending = []
    row = None
    section = None
    for line in (A / "sale-row-events.txt").open(encoding="utf-8-sig"):
        line = line.rstrip("\r\n")
        m = re.match(
            "^### (INSERT INTO|UPDATE|DELETE FROM) `t2ti_bench`\\.`(venda_cabecalho|venda_detalhe|venda_comissao)`",
            line,
            re.I,
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
            require(section, "VERIFICATION_FAILED")
            row[section][int(m[1])] = m[2]
        elif "Xid =" in line:
            order += 1
            selected = []
            for r in pending:
                v = r["after"] or r["before"]
                key = (r["table"], int(v[1]))
                run = owner.get(key)
                if not run:
                    continue
                if r["table"] == "VENDA_CABECALHO":
                    customer_index = next(
                        (
                            i
                            for i, (name, _) in enumerate(columns["VENDA_CABECALHO"], 1)
                            if name == "ID_CLIENTE"
                        )
                    )
                    require(
                        int(v[customer_index]) == packet["expected_customer_id"],
                        "WRONG_CUSTOMER_PARTITION",
                    )
                selected.append((run, r))
                s = stats[key]
                op = {
                    "INSERT INTO": "insert",
                    "DELETE FROM": "delete",
                    "UPDATE": "update",
                }[r["op"]]
                s[op] += 1
                if op in ["insert", "delete"]:
                    s[op + "_order"] = order
                if key in read_expected and op == "insert":
                    if projection_equal(v, read_expected[key], r["table"]):
                        verified_reads[run] += 1
                    else:
                        errors[run]["ORIGINAL_VO_CONTENT_MISMATCH"] += 1
            for run in set((x[0] for x in selected)):
                rows = [r for rr, r in selected if rr == run]
                hs = [r for r in rows if r["table"] == "VENDA_CABECALHO"]
                ds = [r for r in rows if r["table"] == "VENDA_DETALHE"]
                cs = [r for r in rows if r["table"] == "VENDA_COMISSAO"]
                if any((r["op"] == "INSERT INTO" for r in hs)):
                    valid = (
                        len(pending) == len(rows) == 7
                        and len(hs) == len(cs) == 1
                        and (len(ds) == 5)
                        and all((r["op"] == "INSERT INTO" for r in rows))
                    )
                    if valid:
                        h = hs[0]["after"]
                        c = cs[0]["after"]
                        hid = int(h[1])
                        valid = (
                            num(h[20]) == 150
                            and num(h[17]) == 15
                            and (num(c[4]) == 150)
                            and (num(c[6]) == 15)
                            and (int(c[3]) == hid)
                            and (sum((num(r["after"][9]) for r in ds)) == 150)
                            and (sum((num(r["after"][11]) for r in ds)) == 15)
                            and all((int(r["after"][3]) == hid for r in ds))
                        )
                    if valid:
                        create_count[run] += 1
                    else:
                        errors[run]["CREATE_AGGREGATE_ATOMICITY_OR_CONTENT"] += 1
                elif any((r["op"] == "UPDATE" for r in hs)):
                    dd = [r for r in ds if r["op"] == "UPDATE"]
                    added = [r for r in ds if r["op"] == "INSERT INTO"]
                    valid = (
                        len(rows) == len(pending) == 4
                        and len(hs) == len(cs) == len(dd) == len(added) == 1
                        and (num(hs[0]["after"][20]) == 220)
                        and (num(cs[0]["after"][6]) == 22)
                        and (num(dd[0]["after"][4]) == 2)
                        and (num(added[0]["after"][9]) == 60)
                    )
                    if valid:
                        update_count[run] += 1
                    else:
                        errors[run]["UPDATE_AGGREGATE_ATOMICITY_OR_CONTENT"] += 1
                elif any((r["op"] == "DELETE FROM" for r in hs)):
                    valid = (
                        len(hs) == len(cs) == 1
                        and len(ds) in [5, 6]
                        and (len(pending) == len(rows) == len(ds) + 2)
                        and all((r["op"] == "DELETE FROM" for r in rows))
                    )
                    if valid:
                        h = hs[0]["before"]
                        com = cs[0]["before"]
                        hid = int(h[1])
                        valid = (
                            int(com[3]) == hid
                            and all((int(r["before"][3]) == hid for r in ds))
                            and (sum((num(r["before"][9]) for r in ds)) == num(h[20]))
                            and (
                                sum((num(r["before"][11]) for r in ds))
                                == num(com[6])
                                == num(h[17])
                            )
                        )
                    if valid:
                        atomic_deletes[run].add(int(hs[0]["before"][1]))
                    else:
                        errors[run]["DELETE_AGGREGATE_ATOMICITY_OR_CONTENT"] += 1
            pending = []
            row = None
            section = None
    require(not pending, "UNCOMMITTED_TRAILING_ROWS")
    baseline = json.loads((P / "database-verification.json").read_text())
    require("after_content_schema_fk" in baseline, "VERIFICATION_FAILED")
    checks = {}
    for c in cells:
        run = c["run_id"]
        n = len(claims[run]["VENDA_CABECALHO"])
        for table, ids in claims[run].items():
            for i in ids:
                s = stats[table, int(i)]
                if (
                    s["insert"] == s["delete"] == s["update"] == 0
                    and conflict_counts[run]
                ):
                    continue
                if (
                    s["insert"] != 1
                    or s["delete"] != 1
                    or (
                        not (
                            s["insert_order"] is not None
                            and s["delete_order"] is not None
                            and (s["insert_order"] < s["delete_order"])
                        )
                    )
                ):
                    errors[run]["COMMITTED_OWNED_INSERT_DELETE_UNPAIRED"] += 1
        committed_headers = sum(
            (
                stats["VENDA_CABECALHO", int(i)]["insert"]
                for i in claims[run]["VENDA_CABECALHO"]
            )
        )
        if create_count[run] != committed_headers:
            errors[run]["CREATE_COUNT"] += 1
        if c["operation"] == "SALE_CREATE" and create_count[run] != success_counts[run]:
            errors[run]["CREATE_NATIVE_COMMIT_COUNT"] += 1
        for hid in success_headers[run]:
            stat = stats["VENDA_CABECALHO", int(hid)]
            if stat["insert"] != 1 or hid not in atomic_deletes[run]:
                errors[run]["SUCCESS_WITHOUT_OWNED_COMMIT_AND_ATOMIC_DELETE"] += 1
            if c["operation"] == "SALE_UPDATE" and stat["update"] != 1:
                errors[run]["UPDATE_SUCCESS_WITHOUT_COMMITTED_HEADER_UPDATE"] += 1
        if c["operation"] == "SALE_UPDATE" and update_count[run] != success_counts[run]:
            errors[run]["UPDATE_COUNT"] += 1
        if c["operation"] == "SALE_READ" and (
            verified_reads[run] != read_seen[run] or read_seen[run] != n * 7
        ):
            errors[run]["READ_TRANSCRIPT_COUNT_OR_VALUES"] += 1
        good = not errors[run]
        checks[run] = {
            "status": "COMMITTED_SALES_AND_BASELINE_VERIFIED" if good else "FAILED",
            "certification_conflicts_all_phases": conflict_counts[run],
            "claimed_headers": n,
            "committed_headers": committed_headers,
            "creates": create_count[run],
            "updates": update_count[run],
            "original_vo_rows_checked": verified_reads[run],
            "errors": dict(errors[run]),
        }
        c["independent_database_verification"] = checks[run]["status"]
        c["verified_business_goodput_per_second"] = (
            c["worker_reported_throughput_per_second"] if good else None
        )
        c["verified_concurrency_aligned_goodput_per_second"] = (
            c.get("concurrency_aligned", {}).get("worker_reported_operations_second")
            if good
            else None
        )
    report["status"] = "SALES_POSITIVE_CELLS_INDEPENDENT_COMMITTED_ROW_REVIEW"
    (P / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    (P / "sales-stream-verification.json").write_text(
        json.dumps(
            {
                "source_sha256": hashlib.file_digest(
                    (A / "sale-row-events.txt").open("rb"), "sha256"
                ).hexdigest(),
                "commit_order": "Physical decoded transaction order, not Xid numeric order across server restarts",
                "cells": checks,
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(checks))


if __name__ == "__main__":
    run(sys.argv[1])
