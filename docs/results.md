# Results

The accepted dataset comprises 58 performance points measured on 4 and 5 October 2026. One medium-fixture 32-worker READ point is excluded because the worker measurement intervals have no common overlap. Different series remain separate observations; they are not pooled repeated trials.

## Application hosts

The application experiment uses 32 total workers, 100k orders and one shared database. Four application hosts achieved 139.966 CREATE/s, 428.980 READ/s, 108.514 UPDATE/s and 150.296 DELETE/s. Timing synchronization and physical host performance limit interpretation of the observed ratios.

| Configuration | Apps / databases | Fixed USD/h | CREATE/s | READ/s | UPDATE/s | DELETE/s |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1 / 1 | 0.3903 | 46.034 | 28.757 | 24.567 | 40.147 |
| 2 | 2 / 1 | 0.5829 | 112.327 | 192.286 | 85.297 | 116.900 |
| 4 | 4 / 1 | 0.9682 | 139.966 | 428.980 | 108.514 | 150.296 |

## Read routing

Four application hosts and three single-primary cluster members remain present. Increasing eligible read destinations from one to three increased verified READ throughput from 221.227 to 253.679/s, a ratio of 1.147. Application host CPU was approximately 100%.

| Configuration | Apps / databases | Fixed USD/h | CREATE/s | READ/s | UPDATE/s | DELETE/s |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 4 / 3 | 1.3225 | Not measured | 221.227 | Not measured | Not measured |
| 2 | 4 / 3 | 1.3225 | Not measured | 228.544 | Not measured | Not measured |
| 3 | 4 / 3 | 1.3225 | Not measured | 253.679 | Not measured | Not measured |

## Multi-primary write routing

All three cluster members remain writable and present for quorum. Independently owned orders share immutable master references. Certification failures occur at every configuration and reduce verified goodput.

| Configuration | Apps / databases | Fixed USD/h | CREATE/s | READ/s | UPDATE/s | DELETE/s |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 4 / 3 | 1.3225 | 14.327 | Not measured | 5.844 | 6.443 |
| 2 | 4 / 3 | 1.3225 | 43.148 | Not measured | 12.068 | 13.992 |
| 3 | 4 / 3 | 1.3225 | 48.322 | Not measured | 14.093 | 16.258 |

## Shared-record contention

Thirty-two workers update four shared orders. Single-primary throughput was 89.730 verified updates/s. Multi-primary throughput was 69.852/s, 22.15% lower. The multi-primary common interval contains 29,519 failed terminals: 11,315 certification conflicts, 16,476 native deadlocks and 1,764 commit deadlocks. Measured-operation retries were zero. Exact committed increments were verified on all replicas, with no lost updates in the accepted observations.

Successful multi-primary UPDATE p50/p95/p99 were 84.196/286.948/416.075 ms. These quantiles exclude failed operations. Lower successful latency cannot establish improved aggregate outcomes when failure frequency increases.

## Independent shards

Each shard has one application host, eight workers, 100k orders and 500k baseline lines. The experiment uses weak scaling. All twelve accepted shard points have zero measured errors. Physical node performance varies materially despite matching VM and disk classes.

| Configuration | Apps / databases | Fixed USD/h | CREATE/s | READ/s | UPDATE/s | DELETE/s |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1 / 1 | 0.3825 | 25.296 | 14.566 | 20.092 | 24.856 |
| 2 | 2 / 2 | 0.7601 | 97.203 | 59.987 | 78.579 | 97.012 |
| 4 | 4 / 4 | 1.5151 | 194.270 | 138.688 | 168.244 | 204.317 |

## Resource interpretation

| Series | Observations | Interpretation |
|---|---|---|
| Medium CREATE, 32 workers | Application CPU 94.3%; DB CPU 92.6%; DB disk queue 5.8; sampled buffer-hit ratio 1.0; no row-lock-wait increase | Mixed application CPU, database CPU and I/O pressure |
| Medium READ, 16 workers | Application CPU 93.8%; DB CPU 82.8%; disk queue 2.35 | Application CPU and mixed resource pressure; the high-concurrency curve is incomplete |
| Medium UPDATE, 32 workers | Application CPU approximately 100%; DB CPU 46.6%; disk queue 0.83; common interval 23.36s | Application-side CPU pressure is a candidate constraint; short interval limits attribution |
| Application host scaling | Throughput increases at fixed total workers and database count | Distribution improves observed capacity; synchronization and host variation remain confounded |
| Read targets | Near-100% application CPU; 14.7% throughput increase from one to three destinations | Application-side constraint is plausible; database saturation is unestablished |
| Multi-primary writes | Certification failures persist with distinct aggregate ownership | Replication certification materially reduces goodput |
| Shared records | Verified arithmetic, deadlocks and certification failures | Conflict overhead is directly observed |
| Shards | Zero measured errors; per-node throughput and resource variation | Partitioning increases aggregate weak capacity; homogeneous efficiency remains unestablished |

These interpretations are descriptive. Whole-host CPU includes background work and monitoring.

## Data and figures

- [Accepted point table](../results/measurements.csv)
- [Throughput](../results/figures/throughput.png)
- [Successful tail latency](../results/figures/tail-latency.png)
- [Concurrency and quantiles](../results/figures/concurrency.png)
- [Resource observations](../results/figures/resources.png)
- [Failures and contention](../results/figures/conflicts.png)
- [Concurrency resource table](../results/concurrency-resources.csv)
- [Shard resource table](../results/shard-resources.csv)

Each PNG has a corresponding SVG in the figures directory. Source hashes are recorded in [provenance](../evidence/accepted/provenance.json).

## Limitations

The workload uses synthetic fixtures and a 40-table model-derived closure. Original ORM and value objects are exercised; GUI and stock/accounting controller workflows are excluded. READ semantics differ between prepared-owned-aggregate and existing-order series. Preparation and cleanup consume resources outside the timed operation.

The four-host application DELETE point lacks the last 4.885487 seconds of database telemetry. The three-target write DELETE point lacks application CPU for one host. Read collector cadence is uneven and includes gaps. Missing observations remain absent.

Each configuration has one trial. Variability between trials, confidence intervals, statistical significance and production-capacity guarantees are unmeasured. Coverage is limited to the recorded configurations in [study design](study-design.md).
