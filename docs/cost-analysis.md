# Cost analysis

Costs are public on-demand USD estimates using the captured Frankfurt pricing SKUs. Pricing observations were recorded on 5 October 2026; the retained EU machine-image rate was captured on 4 October 2026. Taxes, credits, contract discounts and currency conversion are excluded.

## Topology costs

| Series | Configuration | Applications / databases | Fixed USD/h |
|---|---:|---:|---:|
| Application hosts | 1 | 1 / 1 | 0.3903 |
| Application hosts | 2 | 2 / 1 | 0.5829 |
| Application hosts | 4 | 4 / 1 | 0.9682 |
| Read routing | 1 | 4 / 3 | 1.3225 |
| Read routing | 2 | 4 / 3 | 1.3225 |
| Read routing | 3 | 4 / 3 | 1.3225 |
| Multi-primary writes | 1 | 4 / 3 | 1.3225 |
| Multi-primary writes | 2 | 4 / 3 | 1.3225 |
| Multi-primary writes | 3 | 4 / 3 | 1.3225 |
| Independent shards | 1 | 1 / 1 | 0.3825 |
| Independent shards | 2 | 2 / 2 | 0.7601 |
| Independent shards | 4 | 4 / 4 | 1.5151 |
| Shared-record contention | 1 | 4 / 3 | 1.3225 |
| Shared-record contention | 3 | 4 / 3 | 1.3225 |

All three database members are costed in the cluster comparisons. Increasing eligible destinations changes placement without changing member count. Independent sharding increases both application and database host counts.

Native load generation and Router share application hosts. The estimated topology includes no separate load-generator VM, managed database or paid managed load balancer.

## Pricing components

An e2-standard-2 instance costs USD0.08633556/h for compute and USD0.092/h for Windows Server. An 80-GiB standard disk is USD0.005161/h; an 80-GiB balanced disk is USD0.012903/h. Disk and retained-storage hourly normalization uses the captured catalog base-unit conversion of 744 hours per month.

[Windows Server licensing](https://cloud.google.com/compute/disks-image-pricing#premiumimages) is USD0.046 per visible vCPU/hour. [Cloud NAT](https://cloud.google.com/nat/pricing) adds USD0.0014 per assigned VM/hour, one assumed IP at USD0.005/hour and USD0.045/GiB processed. [VPC pricing](https://cloud.google.com/vpc/network-pricing) provides zero data-transfer charge for the same-zone internal benchmark traffic. External transfer volume is unmeasured.

The selected [SKU records](../evidence/accepted/pricing.json) retain effective times and unit conversions. MySQL and the user-supplied Delphi CE toolchain contribute no incremental license fee in this model.

## Unit cost

| Series | Operation | Lowest observed cost configuration | Operations / USD | USD / million operations |
|---|---|---:|---:|---:|
| Application hosts | CREATE | 2 | 693,713 | 1.442 |
| Application hosts | READ | 4 | 1,595,062 | 0.627 |
| Application hosts | UPDATE | 2 | 526,782 | 1.898 |
| Application hosts | DELETE | 2 | 721,958 | 1.385 |
| Read routing | READ | 3 | 690,543 | 1.448 |
| Multi-primary writes | CREATE | 3 | 131,537 | 7.602 |
| Multi-primary writes | UPDATE | 3 | 38,362 | 26.068 |
| Multi-primary writes | DELETE | 3 | 44,257 | 22.595 |
| Independent shards | CREATE | 4 | 461,588 | 2.166 |
| Independent shards | READ | 4 | 329,525 | 3.035 |
| Independent shards | UPDATE | 4 | 399,750 | 2.502 |
| Independent shards | DELETE | 4 | 485,461 | 2.060 |

Within the fixed-worker application series, two application hosts have the lowest observed CREATE, UPDATE and DELETE unit costs; four hosts have the lowest READ unit cost. Three eligible destinations have the lowest observed unit costs in the fixed-size cluster series. Four shards have the lowest observed unit costs in the weak-scaling series.

These comparisons apply within each series. Workload semantics, synchronization, replication and physical node performance prevent a general production recommendation. Successful operation cost does not account for the application consequences of failed requests.

[Cost-efficiency figure](../results/figures/cost-efficiency.png) and [complete cost table](../results/measurements.csv) include normalized operations per hour, operations per dollar and incremental throughput per incremental dollar. Incremental efficiency is undefined when topology cost is unchanged.

## Infrastructure observation

The pre-deletion fleet comprised nine VMs: four application hosts, four database hosts and one SDK coordinator. Their compute, Windows, disk and fixed NAT estimate was USD1.7078/h. Including known retained storage, the estimate was USD1.7141/h or USD41.14/day. This fleet estimate includes inactive experiment hosts and is separate from the active-topology comparisons.

The [timestamped infrastructure receipt](../evidence/accepted/infrastructure.json) records zero instances, attached disks, NAT routers, reserved addresses and forwarding rules. This receipt is a historical observation, not a live resource inventory.

Three machine images and the database snapshot estimate USD3.96/month. The retained artifact bucket estimates USD0.74/month at the captured size. Combined retained storage is approximately USD4.70/month. Metadata, storage operations, logging and variable transfer are excluded.

## Billing limitations

Actual cumulative project spend is unavailable from the measurement receipts. Creation timestamps do not reconstruct stopped intervals, other deleted environments, failed setup attempts, transfers or credits. Reconciliation requires a Cloud Billing usage export or invoice. No cumulative billed total is inferred.
