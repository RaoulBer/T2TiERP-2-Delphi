# System and workload

## Application boundary

Native Windows workers invoke `TT2TiORM` through Delphi DBExpress and the qualified MySQL driver route. Original value objects provide database mappings. Connections use private same-zone addresses. There is no DataSnap application server in the measured architecture.

The measurements concern the non-GUI worker path. The full ERP client and its reporting dependencies have not been qualified by these experiments.

## Database and fixtures

MySQL 8.4.11 hosts a 40-table foreign-key dependency closure exported from the author's MySQL model. This subset supports the measured sales aggregate and its required references. The author's complete model contains 468 tables.

Baseline fixtures use five lines per order, deterministic reference data and the recorded seed. The medium fixture contains 100k orders and 500k lines. Each independent shard contains that same number of orders and lines, with a distinct customer ownership range. These fixtures are generated data; they are not an imported author-populated ERP database.

The central tables are `VENDA_CABECALHO`, `VENDA_DETALHE` and `VENDA_COMISSAO`. Original mappings, constraints and generated-ID behavior are retained within the selected closure.

## Business operations

| Operation | Database behavior |
|---|---|
| CREATE | Insert a sales header, five lines and a commission in one transaction; order total 150 and commission 15 |
| READ of an existing order | Materialize the header, lines and commission through original value objects |
| READ of an owned aggregate | Prepare an owned order, then time its read; preparation and cleanup contribute resource use outside the read timer |
| UPDATE of an owned aggregate | Change header and commission totals to 220 and 22; update the first line and insert an additional line atomically |
| DELETE | Delete dependent commission and line records, then the owned header in one transaction |
| Shared UPDATE | Lock the selected header, five lines and commission; increment the first line quantity; recompute totals and update three rows atomically |

Native application-host workers construct mapped objects and execute ORM operations within database transactions. Each attempt emits a terminal record after commit or rollback. Database logs and independent observations corroborate the reported outcome.

Untimed setup and cleanup vary by operation. Resource utilization therefore includes work beyond the timed operation. This distinction is retained in the interpretation of throughput and latency.

## Replicated database topology

A three-member MySQL InnoDB Cluster provides the replicated topology. Single-primary mode supports the read-routing experiment. Multi-primary mode supports the write-routing and shared-record comparisons. All three members remain present at every cluster point.

MySQL Router runs locally on each application host. The benchmark explicitly selects eligible read or write destinations. Router changes connection placement; it does not partition application data.

Independently owned orders share master foreign-key references. Certification conflicts remain observable despite distinct aggregate ownership. Failure counts are reported separately from verified successful operations.

## Independent shards

The ownership key is `VENDA_CABECALHO.ID_CLIENTE`. Customer ranges determine shard placement. Headers, lines and commissions are co-located. Global order identity is the customer and local order ID pair.

Known ownership selects one application/database pair. An unowned lookup requires fan-out and disambiguation. Functional fan-out was verified using the same local order ID on four shards; its latency and throughput were not measured. Atomic cross-shard writes are unsupported.

## Hosts

Measured application and database hosts use e2-standard-2 instances with 2 vCPUs and 8 GiB RAM in `europe-west3-c`. Each has an 80-GiB boot disk. Small- and medium-fixture concurrency and application-scaling points use balanced application disks; cluster and shard points use standard application disks. Database disks are balanced. The InnoDB buffer pool is fixed at 2 GiB.

Native load generation and collection run on the application and database hosts. The developer workstation supplies control operations and is outside the timed transaction path. Windows licensing is included in the cost model.
