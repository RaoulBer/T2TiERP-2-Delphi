from lib.errors import require
from pathlib import Path
import json
import math
import collections
import datetime
import hashlib
import sys


def run(directory):
    P = Path(directory).resolve()
    A = P / "actual"
    packet = json.loads((P / "packet.json").read_text())
    cells = []

    def utc(t):
        return datetime.datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()

    def quantile(v, q):
        if not v:
            return None
        v = sorted(v)
        i = (len(v) - 1) * q
        a = int(i)
        return v[a] + (v[min(a + 1, len(v) - 1)] - v[a]) * (i - a)

    for c in packet["cells"]:
        bindings = packet["cell_hosts"][c["run_id"]]
        parts = {
            role: A / (c["run_id"] + "-" + role + "-receipt.json") for role in bindings
        }
        if not all((p.exists() for p in parts.values())):
            continue
        workers_by_id = {}
        host_by_worker = {}
        statuses = []
        for role, path in parts.items():
            raw = json.loads(path.read_text())
            binding = bindings[role]
            require(
                raw["role"] == role
                and str(raw["instance_id"]) == str(packet["hosts"][role]["id"]),
                "VERIFICATION_FAILED",
            )
            require(len(raw["workers"]) == binding["workers"], "VERIFICATION_FAILED")
            statuses.append(raw.get("status"))
            for index, w in enumerate(raw["workers"]):
                worker = binding["worker_offset"] + index
                require(worker not in workers_by_id, "VERIFICATION_FAILED")
                workers_by_id[worker] = w
                host_by_worker[worker] = role
        receipt = {
            "workers": [
                workers_by_id[i] for i in c.get("worker_ids", range(c["workers"]))
            ],
            "status": "HOST_STDERR_PRESENT" if any(statuses) else None,
        }
        lat = []
        measured_terminals = []
        measured_starts = []
        outcomes = collections.Counter()
        started = set()
        terminal = set()
        phase_starts = []
        phase_ends = []
        identities = []
        native_errors = 0
        offered = 0
        certification = collections.Counter()
        missing = []
        worker_finishes = 0
        owned_ids = {
            t: set()
            for t in (
                ["CLIENTE"]
                if c["operation"].startswith("CUSTOMER_")
                else ["VENDA_CABECALHO", "VENDA_DETALHE", "VENDA_COMISSAO"]
            )
        }
        for wi in c.get("worker_ids", range(c["workers"])):
            path = A / (c["run_id"] + "-" + str(wi) + ".ndjson")
            if not path.exists():
                missing.append(wi)
                continue
            expected = workers_by_id[wi]
            require(
                hashlib.sha256(path.read_bytes()).hexdigest()
                == expected["output_sha256"],
                "VERIFICATION_FAILED",
            )
            with path.open(encoding="utf-8-sig") as f:
                for line in f:
                    try:
                        e = json.loads(line)
                    except json.JSONDecodeError:
                        require(
                            receipt.get("status") == "SUPERVISOR_WORKER_TIMEOUT"
                            and (not line.endswith("\n"))
                            and (f.read(1) == ""),
                            "MALFORMED_NATIVE_RECORD",
                        )
                        continue
                    idn = e["identity"]
                    require(
                        idn["run_id"] == c["run_id"]
                        and idn["worker_id"] == wi
                        and (idn["exe_sha256"] == packet["worker_exe_sha256"]),
                        "VERIFICATION_FAILED",
                    )
                    require(
                        str(idn["instance_id"])
                        == packet["hosts"][host_by_worker[wi]]["id"],
                        "VERIFICATION_FAILED",
                    )
                    event = e["event"]
                    if event == "worker_finished":
                        worker_finishes += 1
                    if event == "native_error":
                        native_errors += 1
                    if event == "database_failure":
                        require(
                            e["fields"]["mysql_errno"]
                            in [1180, 3100, 3101, 1213, 1205],
                            "VERIFICATION_FAILED",
                        )
                        certification[e["phase"], str(e["fields"]["mysql_errno"])] += 1
                    for t, ids in e.get(
                        "claimed_owned_ids_require_independent_observation", {}
                    ).items():
                        owned_ids[t].update(ids)
                    if e["phase"] != "MEASUREMENT":
                        continue
                    if event == "attempt_started":
                        offered += 1
                    if event == "phase_started":
                        phase_starts.append(utc(e["observed_utc"]))
                    if event == "phase_terminal":
                        phase_ends.append(utc(e["observed_utc"]))
                    if event == "attempt_started":
                        measured_starts.append(utc(e["observed_utc"]))
                        require(
                            e["global_attempt_id"] not in started, "VERIFICATION_FAILED"
                        )
                        started.add(e["global_attempt_id"])
                    if event == "attempt_terminal":
                        measured_terminals.append(
                            {
                                "utc": utc(e["observed_utc"]),
                                "outcome": e["outcome"],
                                "duration_ms": 1000
                                * e["duration_qpc_ticks"]
                                / e["qpc_frequency"],
                            }
                        )
                        require(
                            e["global_attempt_id"] not in terminal,
                            "VERIFICATION_FAILED",
                        )
                        terminal.add(e["global_attempt_id"])
                        outcomes[e["outcome"]] += 1
                        if e["outcome"] == "COMPLETED_PENDING_INDEPENDENT_OBSERVER":
                            lat.append(
                                1000 * e["duration_qpc_ticks"] / e["qpc_frequency"]
                            )
        elapsed = (
            max(phase_ends) - min(phase_starts) if phase_starts and phase_ends else None
        )
        complete = (
            not missing
            and len(phase_starts) == c["workers"]
            and (len(phase_ends) == c["workers"])
            and (worker_finishes == c["workers"])
            and (not native_errors)
            and all((w["exit_code"] == 0 for w in receipt["workers"]))
            and (terminal == started)
        )
        result = {
            "run_id": c["run_id"],
            "operation": c["operation"],
            "workers": c["workers"],
            "output_capture": c.get("output_capture", "POWERSHELL_ASYNC_STDOUT_PUMP"),
            "supervisor_status": receipt.get("status"),
            "execution_complete": complete,
            "native_errors": native_errors,
            "certification_conflicts": {
                phase + ":" + stage: n for (phase, stage), n in certification.items()
            },
            "measurement_seconds_actual": elapsed,
            "measurement_attempts_offered": offered,
            "measurement_attempts_unstarted_after_setup": offered - len(started),
            "measurement_attempts_started": len(started),
            "measurement_attempts_terminal": len(terminal),
            "outcomes": dict(outcomes),
            "worker_reported_completions": len(lat),
            "worker_reported_throughput_per_second": (
                len(lat) / elapsed if elapsed else None
            ),
            "latency_ms": {
                "p50": quantile(lat, 0.5),
                "p95": quantile(lat, 0.95),
                "p99": quantile(lat, 0.99),
                "min": min(lat) if lat else None,
                "max": max(lat) if lat else None,
            },
            "independent_database_verification": "PENDING",
            "verified_business_goodput_per_second": None,
            "observed_database_owned_id_counts": {
                t: len(v) for t, v in owned_ids.items()
            },
            "measurement_start_utc": (
                datetime.datetime.fromtimestamp(
                    min(phase_starts), datetime.timezone.utc
                ).isoformat()
                if phase_starts
                else None
            ),
            "measurement_end_utc": (
                datetime.datetime.fromtimestamp(
                    max(phase_ends), datetime.timezone.utc
                ).isoformat()
                if phase_ends
                else None
            ),
        }
        result["latency_by_outcome_ms"] = {
            outcome: {
                "samples": sum((e["outcome"] == outcome for e in measured_terminals)),
                **{
                    k: quantile(
                        [
                            e["duration_ms"]
                            for e in measured_terminals
                            if e["outcome"] == outcome
                        ],
                        q,
                    )
                    for k, q in [("p50", 0.5), ("p95", 0.95), ("p99", 0.99)]
                },
            }
            for outcome in outcomes
        }
        if complete:
            shared_start = max(phase_starts)
            shared_end = min(phase_ends)
            shared_seconds = shared_end - shared_start
            if shared_seconds > 0:
                observed = [
                    e
                    for e in measured_terminals
                    if shared_start <= e["utc"] <= shared_end
                ]
                successful = [
                    e["duration_ms"]
                    for e in observed
                    if e["outcome"] == "COMPLETED_PENDING_INDEPENDENT_OBSERVER"
                ]
                result["concurrency_aligned"] = {
                    "active_workers": c["workers"],
                    "seconds": shared_seconds,
                    "start_utc": datetime.datetime.fromtimestamp(
                        shared_start, datetime.timezone.utc
                    ).isoformat(),
                    "end_utc": datetime.datetime.fromtimestamp(
                        shared_end, datetime.timezone.utc
                    ).isoformat(),
                    "successful_completions": len(successful),
                    "attempts_started": sum(
                        (shared_start <= t <= shared_end for t in measured_starts)
                    ),
                    "worker_reported_operations_second": len(successful)
                    / shared_seconds,
                    "failed_terminals": sum(
                        (
                            e["outcome"] != "COMPLETED_PENDING_INDEPENDENT_OBSERVER"
                            for e in observed
                        )
                    ),
                    "latency_ms": {
                        k: quantile(successful, q)
                        for k, q in [("p50", 0.5), ("p95", 0.95), ("p99", 0.99)]
                    },
                    "boundary_disclosure": "Terminal timestamps define common-interval membership. Operations may start before its boundary. Latency uses native QPC; each worker has a nominal 180-second measurement phase.",
                }
            else:
                result["concurrency_aligned"] = {
                    "active_workers": c["workers"],
                    "seconds": 0,
                    "status": "NO_ALL_WORKER_MEASUREMENT_OVERLAP",
                    "start_utc": None,
                    "end_utc": None,
                    "worker_reported_operations_second": None,
                    "latency_ms": None,
                    "failed_terminals": None,
                    "boundary_disclosure": "Worker intervals have no common overlap; fixed-concurrency throughput is undefined.",
                }
        (P / (c["run_id"] + "-owned-ids.json")).write_text(
            json.dumps({t: sorted(v) for t, v in owned_ids.items()}) + "\n"
        )
        cells.append(result)
    report = {
        "status": (
            "MEASURED_NATIVE_CELLS_PENDING_INDEPENDENT_DATABASE_REVIEW"
            if cells
            else "NO_MEASURED_CELLS_RETAINED"
        ),
        "configuration": {
            "database": "MySQL 8.4.11 author-model-derived 40-table closure",
            "dataset_customers": packet["dataset_orders"],
            "dataset_sales": packet["dataset_orders"],
            "dataset_order_lines": packet["dataset_lines"],
            "app_vm": str(packet["app_hosts"])
            + " hosts, each e2-standard-2, 2 vCPU, 8 GiB RAM, Windows Server 2025",
            "database_vm": str(len(packet["database_roles"]))
            + " hosts, each e2-standard-2, 2 vCPU, 8 GiB RAM, Windows Server 2025",
            "disk": packet["disk_description"],
            "network": packet.get(
                "network_description", "private TCP3306, same europe-west3-c zone"
            ),
            "buffer_pool_bytes": 2147483648,
            "phases_seconds": {"warmup": 60, "measurement": 180, "cooldown": 30},
        },
        "cells": cells,
        "limitations": [
            "One trial per configuration; between-trial variance is unmeasured",
            packet["read_semantics"],
            "Original ORM and mapped VOs exercised; GUI/controllers bypassed",
            "Other CRUD setup and cleanup produce database traffic outside the operation latency timer",
            "Per-operation timer includes worker event serialization and output",
            "Worker-reported completions remain distinct from independently verified goodput",
            "No production workload mix or capacity claim",
        ],
    }
    (P / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "status": report["status"],
                "cells": [
                    {
                        "operation": c["operation"],
                        "workers": c["workers"],
                        "complete": c["execution_complete"],
                        "reported_ops_s": c["worker_reported_throughput_per_second"],
                        "p95_ms": c["latency_ms"]["p95"],
                    }
                    for c in cells
                ],
            }
        )
    )


if __name__ == "__main__":
    run(sys.argv[1])
