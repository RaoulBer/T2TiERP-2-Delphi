# Study design

## Objective

Measure the behavior of selected native Delphi sales CRUD operations under controlled concurrency and alternative MySQL deployment topologies. The principal outcomes are verified business operations per second, latency quantiles, failed operations, resource use and estimated topology cost.

## Research questions

1. How does distributing a fixed number of workers across application hosts affect throughput and latency?
2. How does the number of eligible read or write destinations affect performance within a fixed three-member database cluster?
3. How does shared aggregate ownership affect multi-primary write correctness and conflict rates?
4. How does aggregate CRUD capacity change when workers and dataset size increase proportionally with independent shard count?
5. What are the observed costs per verified operation for each measured topology?

## Scope

The workload comprises sales headers, order lines and commissions, with the required customer and master references. Customer CRUD is excluded. MySQL is the selected database. The schema is the author's model-derived 40-table dependency closure. All populated benchmark records are deterministic synthetic data.

Native workers exercise original T2Ti ORM methods and mapped value objects. GUI behavior, controller stock and accounting workflows, production transaction mixes, cross-region deployment and cross-shard atomic transactions are outside the measured scope.

## Recorded configurations

| Series | Recorded configurations | Fixed conditions |
|---|---|---|
| Small fixture CREATE | 1 and 4 workers | 10k orders; one application and one database host |
| Small fixture READ, UPDATE and DELETE | 1 and 4 workers | 10k orders; one application and one database host |
| Medium fixture concurrency | CREATE and UPDATE at 1, 4, 16 and 32; READ at 1, 4 and 16; DELETE at 1 | 100k orders; one application and one database host |
| Application hosts | 1, 2 and 4; all four CRUD operations | 32 total workers; 100k orders; one database host |
| Read destinations | 1, 2 and 3 | Four application hosts; 32 workers; three cluster members; 100k orders |
| Write destinations | 1, 2 and 3; CREATE, UPDATE and DELETE | Four application hosts; 32 workers; three multi-primary members; 100k orders |
| Shared-record contention | Single-primary and multi-primary | Four application hosts; 32 workers; four shared orders |
| Independent shards | 1, 2 and 4; all four CRUD operations | Eight workers, 100k orders and one application host per shard |

The 58 accepted points are enumerated in [the experiment inputs](../experiments). The medium-fixture READ32 concurrency observation is excluded because no complete all-worker measurement interval was available. Application-host comparisons use synchronized workers and existing-fixture READ semantics, defining a separate series.

Each accepted performance point has one trial. Nominal phases are 60 seconds of warmup, 180 seconds of measurement and 30 seconds of cooldown. Native correctness qualification includes atomic CRUD and partial-create rollback within the worker scope.

## Interpretation

Application host and cluster routing comparisons hold total worker count constant. Sharding uses weak scaling: total workers, records and database nodes increase together. Ratios between shard configurations describe observed aggregate capacity. Differences in physical node performance limit inference about homogeneous scaling efficiency.

The study estimates neither a production service-level objective nor a supported user population. Sampling variation between trials, confidence intervals and statistical significance remain unmeasured.
