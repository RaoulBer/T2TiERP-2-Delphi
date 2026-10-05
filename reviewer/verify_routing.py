from lib.errors import require

"Check connection placement and report observed telemetry coverage."
import datetime
import json
import statistics
from pathlib import Path


def utc(value):
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def verify(directory, packet, state, window):
    spec = state["experiment"]
    point = state["configuration"]
    start, end = (utc(window["start_utc"]), utc(window["end_utc"]))
    dbs = packet["database_roles"]
    apps = list(packet["cell_hosts"][state["id"]])
    cluster = spec["routing"] == "router-explicit"
    shards = spec["name"] == "shards-weak"
    target_count = int(point["topology_point"]) if cluster else len(dbs)
    result = {
        "targets": target_count,
        "window_start_utc": window["start_utc"],
        "window_end_utc": window["end_utc"],
        "database": {},
        "application": {},
    }
    for index, db in enumerate(dbs):
        rows = [
            json.loads(line)
            for line in (directory / "actual" / (db + "-metrics.ndjson")).open(
                encoding="utf-8-sig"
            )
            if line.strip()
        ]
        samples = [r for r in rows if start + 3 <= utc(r["utc"]) <= end - 3]
        require(
            samples and (not any((r.get("mysql_error") for r in samples))),
            "MISSING_DATABASE_TELEMETRY",
        )
        counts = []
        members = []
        conflicts = []
        queues = []
        connections = set()
        cache = {}
        for r in samples:
            for line in r["mysql"].splitlines():
                fields = line.split("\t")
                if fields[0] == "HOST_CACHE" and len(fields) > 2 and fields[2]:
                    cache[fields[2]] = fields[1]
        for r in samples:
            require(
                str(r["instance_id"]) == str(packet["hosts"][db]["id"]),
                "TELEMETRY_INSTANCE_BINDING",
            )
            count = 0
            online = 0
            for line in r["mysql"].splitlines():
                f = line.split("\t")
                if f[0] == "BENCH_CONNECTION":
                    count += int(f[-1])
                    host = f[1].split(":")[0]
                    connections.add(cache.get(host, host))
                elif f[0] == "GROUP_MEMBER":
                    online += int(f[2] == "ONLINE")
                elif f[0] == "GROUP_STATS":
                    conflicts.append(int(f[4]))
                    queues.append(int(f[6]))
            counts.append(count)
            members.append(online)
        if cluster:
            require(all((n == 3 for n in members)), "CLUSTER_MEMBER_NOT_ONLINE")
            if index < target_count:
                require(min(counts) > 0, "SELECTED_DATABASE_UNUSED")
            else:
                require(max(counts) == 0, "UNSELECTED_DATABASE_USED")
        elif shards:
            require(all((n == 0 for n in members)), "SHARD_REPLICATED")
        expected_apps = [apps[index]] if shards else apps
        expected_ips = {packet["hosts"][a]["ip"] for a in expected_apps}
        require(
            connections <= expected_ips,
            "WRONG_APPLICATION_CONNECTION_OR_UNRESOLVED_HOST_ALIAS",
        )
        if not cluster or index < target_count:
            require(connections, "NO_NATIVE_BENCH_CONNECTION_OBSERVED")
        if shards:
            require(connections == expected_ips, "WRONG_SHARD_PLACEMENT")
        times = [utc(r["utc"]) for r in samples]
        cpu = [r["cpu"] for r in samples if r.get("cpu") is not None]
        result["database"][db] = {
            "samples": len(samples),
            "cpu_mean_percent": statistics.mean(cpu) if cpu else None,
            "cpu_samples": len(cpu),
            "maximum_sample_gap_seconds": max(
                (b - a for a, b in zip(times, times[1:])), default=None
            ),
            "connections_min": min(counts),
            "connections_max": max(counts),
            "observed_application_ips": sorted(connections),
            "remote_applier_queue_max": max(queues) if queues else None,
            "certification_conflicts_max": max(conflicts) if conflicts else None,
        }
    for app in apps:
        rows = [
            json.loads(line)
            for line in (directory / "actual" / (app + "-metrics.ndjson")).open(
                encoding="utf-8-sig"
            )
            if line.strip()
        ]
        rows = [r for r in rows if start <= utc(r["utc"]) <= end]
        values = [r["cpu"] for r in rows if r.get("cpu") is not None]
        times = [utc(r["utc"]) for r in rows]
        result["application"][app] = {
            "samples": len(rows),
            "cpu_mean_percent": statistics.mean(values) if values else None,
            "cpu_samples": len(values),
            "maximum_sample_gap_seconds": max(
                (b - a for a, b in zip(times, times[1:])), default=None
            ),
            "coverage": "Observed samples only; absent counters remain null",
        }
    (directory / "routing-and-resources.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    return result
