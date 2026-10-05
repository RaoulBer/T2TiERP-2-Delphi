# Experimental methods

## Measurement intervals

Each configuration has one trial with nominal 60-second warmup, 180-second measurement and 30-second cooldown phases. Native event records identify workers, operations, phases, outcomes and timestamps. Latency is measured with the Windows high-resolution performance counter.

For concurrent comparisons, throughput is calculated over the intersection of worker measurement intervals:

```text
verified throughput = verified successful terminals / common interval duration
```

The common interval can be shorter than the per-worker 180-second phase. An operation can start before the common boundary and terminate within it. These boundary conditions are preserved in the interpretation of terminal-count throughput.

The medium-fixture 32-worker READ point has no all-worker common measurement interval and is excluded from the concurrency curve. Synchronized topology comparisons form separate series because timing and workload semantics differ.

## Latency and failures

Report p50, p95 and p99 latency for successful operations. Report failed terminals separately. For points with a retained common duration, failure fraction is:

```text
failed terminals / (failed terminals + verified successful terminals)
```

Certification conflicts, native deadlocks, commit deadlocks, lock timeouts and other failures retain distinct classifications. Shared-record contention has no measured-operation retries. Unknown failures remain fatal to acceptance where required by the worker protocol.

Preparation and cleanup can generate database traffic outside the timed operation. Monitoring and event serialization also consume resources. The measurements include their documented overhead.

## Correctness

Successful worker outcomes require independent corroboration. The observations include committed MySQL ROW/FULL events, transaction grouping, generated IDs, header and line totals, commission values, returned original value objects and owned cleanup.

Full baseline content, schema and foreign-key observations verify restoration within the selected 40-table closure. Generated-ID counters can advance and are disclosed. Replicated experiments require consistent accepted state on all three members. Shared-record experiments verify exact committed increments and preservation of unrelated rows.

Routing observations identify the expected application-to-database connections. Native hostname-to-address observations support connection checks when MySQL reverse DNS returns hostnames.

## Resource observations

Collectors sample host CPU, available memory, disk throughput and queues, network activity and selected process statistics. MySQL counters include connections, running threads, buffer reads, row locks and transaction activity. Requested sampling cadence and observed gaps are recorded separately.

Derived resource summaries use observed samples within the recorded intervals. Missing samples remain absent. They are not interpolated or assigned zero. Whole-host CPU includes monitoring and unrelated processes; it is not equivalent to worker CPU.

## Statistical scope

The analysis is descriptive. Each configuration was executed once. Quantiles characterize transactions within a trial. They do not estimate variability between independent trials. Confidence intervals, significance tests and production-capacity estimates are outside the available evidence.

Comparisons require matching workload semantics, worker counts, data placement and topology definitions. Weak scaling and fixed-load comparisons remain distinct. A bottleneck interpretation requires multiple supporting signals and may remain mixed or unresolved.

## Cost normalization

Topology cost includes active application and database hosts, Windows licensing, their disks and fixed NAT assumptions. Three cluster members are counted even when fewer members accept routed traffic. Costs of retained idle hosts and backups are reported separately.

```text
operations per hour = verified operations per second × 3600
operations per dollar = operations per hour / topology cost per hour
USD per million operations = topology cost per hour × 1,000,000 / operations per hour
```

These calculations normalize observed rates. They do not represent measured one-hour workloads or actual invoices.
