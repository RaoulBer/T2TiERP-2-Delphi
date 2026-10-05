"""Admit results only after native identity, committed rows and fixture validation."""

from lib.errors import require

from pathlib import Path
import csv
import json
import shutil
from verify_capture import verify_pair, digest
from verify_routing import verify as verify_routing

ROOT = Path(__file__).resolve().parents[1]


def invoke(name, directory):
    import contextlib
    import importlib
    import io

    processor = importlib.import_module(Path(name).stem)
    with contextlib.redirect_stdout(io.StringIO()):
        processor.run(directory)


def point_orders(state):
    return state["configuration"]["orders"]


def verify(directory):
    state = json.loads((directory / "run.json").read_text())
    packet = json.loads((directory / "packet.json").read_text())
    raw = directory / "actual"
    manifest = json.loads((directory / "raw-manifest.json").read_text())
    for name, hash_ in manifest["files"].items():
        require(digest(raw / name) == hash_, "RAW_CHECKSUM")
    run = state["id"]
    shards = state["experiment"]["name"] == "shards-weak"
    contention = state["experiment"]["name"] == "contention"
    existing = (
        state["experiment"]["read_semantics"] == "existing fixture"
        and state["configuration"]["operation"] == "READ"
    )
    databases = packet["database_roles"]
    results = []
    for db in databases:
        observer = json.loads((raw / (db + "-observer.json")).read_text())
        require(
            observer["status"] == "OBSERVATION_COMPLETE"
            and str(observer["instance_id"]) == str(packet["hosts"][db]["id"]),
            "VERIFICATION_FAILED",
        )
        fixture = (
            directory
            / "fixtures"
            / (db if shards else "db-1")
            / "dataset-manifest.json"
        )
        if not contention:
            verify_pair(
                fixture,
                raw / (db + "-before.tsv"),
                raw / (db + "-after.tsv"),
                directory / ("captures-" + db),
            )
    groups = (
        [
            (
                db,
                [
                    a
                    for a in packet["cell_hosts"][run]
                    if int(a.split("-")[1]) == int(db.split("-")[1])
                ],
            )
            for db in databases
        ]
        if shards
        else [("db-1", list(packet["cell_hosts"][run]))]
    )
    for db, apps in groups:
        group = directory / "verification" / db
        actual = group / "actual"
        actual.mkdir(parents=True, exist_ok=True)
        local = json.loads(json.dumps(packet))
        bindings = {a: packet["cell_hosts"][run][a] for a in apps}
        worker_ids = sorted(
            (
                i
                for b in bindings.values()
                for i in range(b["worker_offset"], b["worker_offset"] + b["workers"])
            )
        )
        local["cells"][0]["workers"] = len(worker_ids)
        local["cells"][0]["worker_ids"] = worker_ids
        local["cell_hosts"][run] = bindings
        local["app_hosts"] = len(apps)
        local["dataset_orders"] = (
            state["experiment"]["orders_per_node"] if shards else point_orders(state)
        )
        local["dataset_lines"] = local["dataset_orders"] * 5
        local["expected_customer_id"] = (
            (int(db.split("-")[1]) - 1) * state["experiment"]["orders_per_node"] + 1
            if shards
            else 1
        )
        (group / "packet.json").write_text(json.dumps(local, indent=2) + "\n")
        for app in apps:
            shutil.copy2(
                raw / (run + "-" + app + "-receipt.json"),
                actual / (run + "-" + app + "-receipt.json"),
            )
        for worker in worker_ids:
            shutil.copy2(
                raw / (run + "-" + str(worker) + ".ndjson"),
                actual / (run + "-" + str(worker) + ".ndjson"),
            )
        for source, target in [
            (db + "-before.tsv", "db-before.tsv"),
            (db + "-after.tsv", "db-after.tsv"),
            (db + "-sale-row-events.txt", "sale-row-events.txt"),
        ]:
            shutil.copy2(raw / source, actual / target)
        if contention:
            for replica in databases:
                shutil.copy2(
                    raw / (replica + "-after.tsv"), actual / (replica + "-after.tsv")
                )
        invoke("summarize.py", group)
        parsed = json.loads((group / "results.json").read_text())
        require(
            len(parsed["cells"]) == 1 and parsed["cells"][0]["execution_complete"],
            "INCOMPLETE_NATIVE_EXECUTION",
        )
        require(
            parsed["cells"][0]["concurrency_aligned"]["seconds"] > 0,
            "NO_SHARED_MEASUREMENT_INTERVAL",
        )
        if contention:
            invoke("verify_contention.py", group)
            parsed["cells"][0]["independent_database_verification"] = json.loads(
                (group / "contention-verification.json").read_text()
            )["status"]
            parsed["cells"][0]["verified_concurrency_aligned_goodput_per_second"] = (
                parsed["cells"][0]["concurrency_aligned"][
                    "worker_reported_operations_second"
                ]
            )
            (group / "results.json").write_text(json.dumps(parsed, indent=2) + "\n")
        else:
            shutil.copy2(
                directory / ("captures-" + db) / "database-verification.json",
                group / "database-verification.json",
            )
            if existing:
                invoke("verify_existing_reads.py", group)
            else:
                invoke("verify_shard_sales.py", group)
        parsed = json.loads((group / "results.json").read_text())
        cell = parsed["cells"][0]
        require(
            cell.get("verified_concurrency_aligned_goodput_per_second") is not None,
            "INDEPENDENT_VERIFICATION_FAILED",
        )
        results.append({"database": db, **cell})
    global_ = json.loads((directory / "results.json").read_text())["cells"][0]
    require(
        global_["execution_complete"] and global_["concurrency_aligned"]["seconds"] > 0,
        "VERIFICATION_FAILED",
    )
    routing = verify_routing(directory, packet, state, global_["concurrency_aligned"])
    report = {
        "routing_and_resources": routing,
        "status": "NATIVE_AND_INDEPENDENT_DATABASE_VERIFIED",
        "run_id": run,
        "experiment": state["experiment"]["name"],
        "configuration": state["configuration"],
        "node_verification": results,
        "concurrency_aligned": global_["concurrency_aligned"],
        "raw_manifest_sha256": digest(directory / "raw-manifest.json"),
    }
    (directory / "verified-results.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    window = global_["concurrency_aligned"]
    row = {
        "series": report["experiment"],
        "topology_point": state["configuration"]["topology_point"],
        "operation": state["configuration"]["operation"],
        "workers": state["configuration"]["workers"],
        "verified_tx_s": window["worker_reported_operations_second"],
        "p50_ms": window["latency_ms"]["p50"],
        "p95_ms": window["latency_ms"]["p95"],
        "p99_ms": window["latency_ms"]["p99"],
        "failed_terminals": window["failed_terminals"],
        "shared_measurement_seconds": window["seconds"],
    }
    with (directory / "measurements.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=row)
        writer.writeheader()
        writer.writerow(row)
    return {"status": report["status"], "run_id": run, "measurement": row}
