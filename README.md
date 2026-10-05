# Native Delphi sales workload: scaling results and reproduction

This study measures sales CRUD operations executed through original T2Ti ORM and value objects using Delphi DBExpress and MySQL 8.4.11. The database is a 40-table foreign-key dependency closure of the author's 468-table MySQL model. Fixtures contain deterministic synthetic data. The accepted dataset comprises **58 configurations from eight series**, measured on 4 and 5 October 2026.

## Source and scope

This repository is a research branch of [RaoulBer/T2TiERP-2-Delphi](https://github.com/RaoulBer/T2TiERP-2-Delphi), forked from [Albert Eije's T2Ti ERP](https://github.com/alberteije/T2TiERP-2-Delphi). The base commit is [`277a36d`](https://github.com/alberteije/T2TiERP-2-Delphi/commit/277a36dea23ed2de1f651aa99cd7fb797743c576). Original application files remain in `Retaguarda`, `Frente de Caixa` and the supporting tool directories. The original [ERP description](https://github.com/alberteije/T2TiERP-2-Delphi/blob/277a36dea23ed2de1f651aa99cd7fb797743c576/README.md) documents its modules and architecture.

Research additions are confined to the benchmark, infrastructure, reviewer, analysis, documentation and evidence paths. All 28 retained ERP dependency units match the base commit exactly. The benchmark uses frozen source snapshots; the full application and GUI workflows are outside the measured scope.

## Principal results

Throughput counts independently verified successful business operations. Latency quantiles describe successful operations only. Each configuration has one trial; ratios are descriptive, without confidence intervals or significance tests.

| Comparison | Verified operations/s | Successful p95, ms | Measured failures | Estimated USD/h |
|---|---:|---:|---|---:|
| Applications: 1 → 4 hosts, CREATE | 46.034 → 139.966 | 1043.492 → 277.025 | 0 | 0.3903 → 0.9682 |
| Applications: 1 → 4 hosts, READ | 28.757 → 428.980 | 4971.558 → 163.249 | 0 | 0.3903 → 0.9682 |
| Read routing: 1 → 3 destinations | 221.227 → 253.679 | 916.948 → 689.965 | 0 | 1.3225 |
| Multi-primary writes: 1 → 3 destinations, CREATE | 14.327 → 48.322 | 279.473 → 173.403 | 86.91% → 73.70% | 1.3225 |
| Shared UPDATE: single → multi-primary | 89.730 → 69.852 | 809.801 → 286.948 | 29,519 multi-primary failures | 1.3225 |
| Independent shards: 1 → 4, CREATE | 25.296 → 194.270 | 324.766 → 238.570 | 0 | 0.3825 → 1.5151 |

Application and cluster comparisons use 32 total workers. Cluster comparisons retain three database members and four application hosts. Sharding uses weak scaling: eight workers, one application host and 100k orders per shard. Concurrency and shard READ operations time prepared, owned aggregates; application-scaling and cluster read routing time existing fixture orders. Rates from different series are not interchangeable.

Read routing increased observed throughput by 14.7%, with application CPU near 100%. Multi-primary certification and deadlock failures reduced successful throughput. Shared-record arithmetic was verified on every replica, with no lost updates in the accepted observations. Shard capacity increased with proportional resources; physical host variation limits attribution to homogeneous scaling efficiency.

[Complete results](docs/results.md), [all measurements](results/measurements.csv), [throughput figure](results/figures/throughput.png) and [cost analysis](docs/cost-analysis.md) provide intermediate configurations, CRUD coverage and resource observations. Cost values are captured on-demand estimates, not invoices. Retained storage was estimated at approximately USD4.70/month at the recorded observation.

## Reproduce the analysis

From a checkout, with Python and the pinned analysis dependency:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/analyze.py
python3 scripts/validate_repository.py
python3 reviewer/validate.py
python3 scripts/validate_upstream.py
python3 -m unittest discover -s reviewer -p 'test_*.py'
```

These commands regenerate six figures, the measurement CSV and the results and cost documents from [accepted inputs](evidence/accepted). They perform no cloud operations. Historical raw traces are not distributed; their checksums identify the observations underlying the accepted dataset.

## Reproduce a measurement

Requirements are a licensed Windows Delphi Win32 installation, the [pinned dependencies](benchmark/dependencies.json), Terraform and authenticated GCP CLI access. Build the [frozen native sources](benchmark/source-manifest.json) with `reviewer/build.ps1`. Copy [the configuration example](reviewer/config.example.json) to ignored `reviewer/config.json` and specify an independent project, resource prefix, bucket and input paths.

```sh
python3 reviewer/workflow.py configure --series read-targets --point 2 --operation READ
```

Use the printed directory in place of `RUN_ID`. Storage and workload have separate Terraform states:

```sh
python3 reviewer/workflow.py plan --run reviewer/runs/RUN_ID
python3 reviewer/workflow.py apply --run reviewer/runs/RUN_ID
python3 reviewer/workflow.py plan --run reviewer/runs/RUN_ID
python3 reviewer/workflow.py apply --run reviewer/runs/RUN_ID
python3 reviewer/workflow.py prepare --run reviewer/runs/RUN_ID
python3 reviewer/workflow.py measure --run reviewer/runs/RUN_ID
python3 reviewer/workflow.py collect --run reviewer/runs/RUN_ID
python3 reviewer/workflow.py verify --run reviewer/runs/RUN_ID
python3 reviewer/workflow.py destroy --run reviewer/runs/RUN_ID
```

Provisioning creates billable resources. `destroy` removes workload compute and networking while retaining evidence storage and its charges. The distributed scripts have offline validation, including retained native-observation checks. **Fresh Windows compilation and cloud execution of the refactored package remain unverified.** See [reproduction instructions](docs/reproducibility.md) for prerequisites, verification and state ownership.

## Scope and evidence

The measured path excludes GUI execution and stock/accounting controller workflows. All configurations use 60-second warmup, 180-second measurement and 30-second cooldown phases. Throughput uses the common worker interval, which may be shorter than 180 seconds. The medium-fixture READ32 point is excluded for lack of a common interval. Missing telemetry remains absent.

[Study design](docs/study-design.md), [system and transactions](docs/system-and-workload.md), [methods](docs/experimental-methods.md) and [validation record](evidence/reproducibility.json) define the evidence boundaries. Software versions, timestamps and checksums are experimental metadata; Git records document revisions. Publication requires explicit approval.
