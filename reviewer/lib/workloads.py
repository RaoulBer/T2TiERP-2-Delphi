def worker_profile(spec, cell):
    baseline = spec["worker_profile"] == "baseline"
    router = spec["routing"] == "router-explicit"
    if baseline:
        executable = "SalePerformance.exe"
    elif spec["worker_profile"] == "contention":
        executable = "SaleSharedContention.exe"
    elif spec["name"] == "write-targets":
        executable = "SaleConflictPerformance.exe"
    else:
        executable = "SaleSynchronizedPerformance.exe"
    if cell["operation"] == "READ" and spec["read_semantics"] == "existing fixture":
        executable = "SaleInquirySynchronizedPerformance.exe"
    return {
        "worker_executable": executable,
        "synchronized": not baseline,
        "route_kind": (
            "read"
            if spec["name"] == "read-targets"
            else "write" if router else "direct"
        ),
        "shared_pool_size": spec["shared_orders"],
        "launch_stagger_ms": 200 if router else 0,
        "fail_fast": router,
    }
