from pathlib import Path
import sys
from .paths import ROOT, RUNTIME, AUTHOR
from .files import read, write, sha, command, utc_after
from .workloads import worker_profile


def initialize_database(t):
    spec = t.s["experiment"]
    p = t.s["configuration"]
    phase = t.s["id"] + "-prepare"
    cluster = p["database_vms"] == 3 and spec["name"] != "shards-weak"
    names = ["mysql.zip", "vc_redist.x64.exe"] + (["shell.zip"] if cluster else [])
    dependencies = t.dependencies(names)
    for role, host in t.hosts.items():
        if not role.startswith("db-"):
            continue
        fixture_role = role if spec["name"] == "shards-weak" else "db-1"
        fixture = t.directory / "fixtures" / fixture_role
        import_ = not cluster or role == "db-1"
        assets = [*dependencies, t.credentials()]
        if import_:
            assets += [
                t.asset(AUTHOR / "schema.sql"),
                t.asset(AUTHOR / "views.sql"),
                t.asset(fixture / "dataset.sql.gz"),
                t.asset(fixture / "verification.sql"),
            ]
        payload = {
            "ip": host["ip"],
            "server_id": int(role.split("-")[1]),
            "cluster": cluster,
            "import_fixture": import_,
            "private_cidr": t.c["private_cidr"],
            "mysql_host_pattern": t.c["private_cidr"].rsplit(".", 1)[0] + ".%",
            "dataset_sql_sha256": t.s["fixtures"][fixture_role]["dataset_sql_sha256"],
        }
        t.dispatch(role, phase, "setup-database.ps1", payload, assets)
    dbs = [r + "-setup.json" for r in t.hosts if r.startswith("db-")]
    t.wait(phase, dbs, {"DATABASE_INITIALIZED"})
    if cluster:
        assets = [t.credentials(), t.asset(RUNTIME / "cluster.js")]
        t.dispatch(
            "db-1",
            phase,
            "configure-cluster.ps1",
            {
                "cluster_control": {
                    "action": "create",
                    "ips": [t.hosts["db-" + str(i)]["ip"] for i in range(1, 4)],
                }
            },
            assets,
        )
        t.wait(phase, ["cluster-create.json"], {"CLUSTER_CONFIGURED"})
    t.s["status"] = "DATABASES_PREPARED_PENDING_CAPTURE_VALIDATION"
    write(t.directory / "run.json", t.s)


def switch_mode(t, phase, action):
    t.dispatch(
        "db-1",
        phase,
        "configure-cluster.ps1",
        {
            "cluster_control": {
                "action": action,
                "ips": [t.hosts["db-" + str(i)]["ip"] for i in range(1, 4)],
            }
        },
        [t.credentials(), t.asset(RUNTIME / "cluster.js")],
    )
    t.wait(phase, ["cluster-" + action + ".json"], {"CLUSTER_CONFIGURED"})


def measure(t):
    spec = t.s["experiment"]
    p = t.s["configuration"]
    phase = t.s["id"] + "-measure"
    apps = sorted(r for r in t.hosts if r.startswith("app-"))
    dbs = sorted(r for r in t.hosts if r.startswith("db-"))
    shards = spec["name"] == "shards-weak"
    profile = worker_profile(spec, p)
    baseline = not profile["synchronized"]
    if len(dbs) == 3 and not shards:
        action = (
            "multi"
            if spec["name"] == "write-targets"
            or (
                spec["name"] == "contention"
                and str(p["topology_point"]) in ["multi-primary", "multi", "3"]
            )
            else "single"
        )
        switch_mode(t, phase + "-mode", action)
    stop = utc_after(5400)
    workers = p["workers"] // len(apps)
    run = t.s["id"]
    native = Path(t.c["native_inputs"])
    build = read(native / "build-receipt.json")
    if build["source_manifest_sha256"] != sha(ROOT / "benchmark/source-manifest.json"):
        raise ValueError("Native build source manifest differs")
    source_manifest = build["source_manifest_sha256"]
    exe = profile["worker_executable"]
    artifacts = {a["name"]: a["sha256"] for a in build["artifacts"]}
    for name in [exe, "dbxoodbc.dll", "dbxadapter.dll"]:
        if sha(native / name) != artifacts[name]:
            raise ValueError("Native artifact differs from build receipt: " + name)
    cell = {
        "run_id": run,
        "operation": "SALE_" + p["operation"],
        "workers": p["workers"],
        "write_targets": (
            p["topology_point"]
            if spec["name"] in ["write-targets", "contention"]
            else 1
        ),
        "read_targets": p["topology_point"] if spec["name"] == "read-targets" else 1,
    }
    if exe == "SaleInquirySynchronizedPerformance.exe":
        cell["read_mode"] = "EXISTING_FIXTURE"
    dependencies = t.dependencies(
        ["odbc.zip", "vc_redist.x86.exe", "vc_redist.x64.exe"]
        + (["router.zip"] if spec["routing"] == "router-explicit" else [])
    )
    assets = [
        *dependencies,
        t.asset(native / exe),
        t.asset(native / "dbxoodbc.dll"),
        t.asset(native / "dbxadapter.dll"),
        t.asset(
            AUTHOR / "qualification-receipt.json", "parent-qualification-receipt.json"
        ),
        t.asset(RUNTIME / "sampler.ps1"),
    ]
    packet = {
        "cells": [cell],
        "hosts": t.hosts,
        "cell_hosts": {run: {}},
        "database_roles": dbs,
        "worker_exe_sha256": sha(native / exe),
        "dataset_orders": p["orders"],
        "dataset_lines": p["orders"] * 5,
        "app_hosts": len(apps),
        "disk_description": "80 GiB "
        + spec["application_disk_type"]
        + "/application; 80 GiB pd-balanced/database",
        "network_description": "private TCP3306, same " + t.c["zone"] + " zone",
        "read_semantics": spec["read_semantics"],
        "experiment": spec["name"],
        "assets": {a["name"]: a for a in assets},
    }
    for db in dbs:
        fixture_role = db if shards else "db-1"
        fixture = t.directory / "fixtures" / fixture_role
        database_apps = [apps[dbs.index(db)]] if shards else apps
        t.dispatch(
            db,
            phase,
            "observe-database.ps1",
            {
                "application_roles": database_apps,
                "stop_utc": stop,
                "baselines": {
                    "header": spec["orders_per_node"] if shards else p["orders"],
                    "detail": (spec["orders_per_node"] if shards else p["orders"]) * 5,
                    "commission": spec["orders_per_node"] if shards else p["orders"],
                },
            },
            [t.credentials(), t.asset(fixture / "verification.sql")],
        )
    t.wait(phase, [db + "-ready.json" for db in dbs], {"READY"})
    # Capture validation is required before timed workers are dispatched.
    command(
        [
            "gcloud",
            "storage",
            "rsync",
            "gs://" + t.bucket + "/results/" + phase + "/benchmark",
            str(t.directory / "actual"),
            "--quiet",
        ],
        capture=True,
    )
    from verify_capture import verify_pair

    for db in dbs:
        fixture_role = db if shards else "db-1"
        verify_pair(
            t.directory / "fixtures" / fixture_role / "dataset-manifest.json",
            t.directory / "actual" / (db + "-before.tsv"),
            None,
            t.directory / ("initial-" + db),
        )
    for i, app in enumerate(apps):
        db = dbs[i] if shards else dbs[0]
        binding = {"workers": workers, "worker_offset": i * workers}
        packet["cell_hosts"][run][app] = binding
        localcell = {**cell, "workers": workers}
        payload = {
            "run_id": run,
            "stop_utc": stop,
            "synchronized": not baseline,
            "cells": [localcell],
            "worker_offset": i * workers,
            "app_index": i,
            "database_role": db,
            "database_instance_id": t.hosts[db]["id"],
            "database_ip": (
                "127.0.0.1"
                if spec["routing"] == "router-explicit"
                else t.hosts[db]["ip"]
            ),
            "source_manifest_sha256": source_manifest,
            "inquiry_source_manifest_sha256": source_manifest,
            "write_target_ips": [t.hosts[x]["ip"] for x in dbs],
            "read_target_ips": [t.hosts[x]["ip"] for x in dbs],
            "customer_id": (i * spec["orders_per_node"] + 1) if shards else 1,
        }
        payload.update(profile)
        t.dispatch(
            app, phase, "run-application.ps1", payload, [*assets, t.credentials()]
        )
    write(t.directory / "packet.json", packet)
    if not baseline:
        for suffix in ["", "-measurement"]:
            names = [run + "-" + app + suffix + "-ready.json" for app in apps]
            t.wait(phase, names, {"HOST_READY"}, timeout=2400)
            receipts = [t.fetch(phase, n) for n in names]
            if sum(r["workers"] for r in receipts) != p["workers"]:
                raise ValueError("Barrier worker count differs")
            for r in receipts:
                if str(r["instance_id"]) != str(t.hosts[r["role"]]["id"]):
                    raise ValueError("Barrier host binding differs")
            start = {
                "status": "START",
                "run_id": run,
                "start_utc": utc_after(15),
                "total_workers": p["workers"],
            }
            path = t.directory / (run + suffix + "-start.json")
            write(path, start)
            t.upload(path, "results/" + phase + "/benchmark/" + path.name)
    t.wait(phase, [app + "-final.json" for app in apps], {"FINISHED"}, timeout=2400)
    t.wait(
        phase,
        [db + "-observer.json" for db in dbs],
        {"OBSERVATION_COMPLETE"},
        timeout=2400,
    )
    t.s["measurement_phase"] = phase
    t.s["status"] = "MEASURED_PENDING_INDEPENDENT_VERIFICATION"
    write(t.directory / "run.json", t.s)


def collect(t):
    phase = t.s.get("measurement_phase", t.s["id"] + "-measure")
    (t.directory / "actual").mkdir(exist_ok=True)
    command(
        [
            "gcloud",
            "storage",
            "rsync",
            "gs://" + t.bucket + "/results/" + phase + "/benchmark",
            str(t.directory / "actual"),
            "--quiet",
        ],
        capture=True,
    )
    command([sys.executable, ROOT / "reviewer/summarize.py", t.directory])
    checks = {
        p.name: sha(p)
        for p in sorted((t.directory / "actual").iterdir())
        if p.is_file()
    }
    write(
        t.directory / "raw-manifest.json",
        {
            "files": checks,
            "source_manifest_sha256": sha(ROOT / "benchmark/source-manifest.json"),
        },
    )
