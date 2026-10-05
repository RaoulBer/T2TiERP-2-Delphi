"""Generate descriptive tables and figures from accepted local measurements."""

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

matplotlib.rcParams["svg.hashsalt"] = "t2ti-scaling-study"

ROOT = Path(__file__).resolve().parents[1]
ACCEPTED = ROOT / "evidence/accepted"
RESULTS = ROOT / "results"
FIGURES = RESULTS / "figures"
OPERATIONS = ["CREATE", "READ", "UPDATE", "DELETE"]
SERIES = {
    "application-scaling": ("Application hosts", "Application hosts"),
    "read-targets": ("Read routing", "Eligible read targets"),
    "write-targets": ("Multi-primary writes", "Eligible write targets"),
    "shards-weak": ("Independent shards", "Shard count"),
    "contention": ("Shared-record contention", "Write targets"),
}


def read(path):
    return json.loads(path.read_text())


def selected(points, series, operation=None):
    return sorted(
        [
            p
            for p in points
            if p["series"] == series
            and (operation is None or p["operation"] == operation)
        ],
        key=lambda p: p["topology_point"],
    )


def matrix(points, series):
    rows = selected(points, series)
    lines = [
        "| Configuration | Apps / databases | Fixed USD/h | CREATE/s | READ/s | UPDATE/s | DELETE/s |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for x in sorted({r["topology_point"] for r in rows}):
        group = [r for r in rows if r["topology_point"] == x]
        first = group[0]
        rates = {r["operation"]: r["verified_tx_s"] for r in group}
        values = " | ".join(
            f"{rates[op]:.3f}" if op in rates else "Not measured" for op in OPERATIONS
        )
        lines.append(
            f"| {x} | {first['application_vms']} / {first['database_vms']} | "
            f"{first['topology_fixed_usd_hour']:.4f} | {values} |"
        )
    return "\n".join(lines)


def save(fig, name):
    fig.tight_layout()
    for suffix in ["png", "svg"]:
        metadata = {"Date": None} if suffix == "svg" else None
        path = FIGURES / f"{name}.{suffix}"
        fig.savefig(path, dpi=170, metadata=metadata)
        if suffix == "svg":
            path.write_text(
                "\n".join(line.rstrip() for line in path.read_text().splitlines())
                + "\n"
            )
    plt.close(fig)


def topology_figure(points, field, ylabel, name):
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    for (series, (title, xlabel)), ax in zip(SERIES.items(), axes.flat):
        for op in OPERATIONS:
            rows = selected(points, series, op)
            if rows:
                ax.plot(
                    [r["topology_point"] for r in rows],
                    [r[field] for r in rows],
                    "o-",
                    label=op,
                )
        ax.set_title(title)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_xticks(sorted({r["topology_point"] for r in selected(points, series)}))
        ax.grid(alpha=0.25)
        ax.legend()
    axes[1, 2].axis("off")
    axes[1, 2].text(
        0,
        0.9,
        "One trial per configuration\nCluster: three members at every point\nShards: eight workers and 100k orders per node\nSeries have different workload semantics",
        va="top",
    )
    save(fig, name)


def figures(points):
    topology_figure(points, "verified_tx_s", "Verified operations/s", "throughput")
    topology_figure(points, "p95_ms", "Successful operation p95 (ms)", "tail-latency")
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    for series, ax in zip(
        ["application-scaling", "write-targets", "shards-weak"], axes
    ):
        title, xlabel = SERIES[series]
        for op in OPERATIONS:
            rows = selected(points, series, op)
            if rows:
                ax.plot(
                    [r["topology_point"] for r in rows],
                    [r["usd_per_million_verified_operations"] for r in rows],
                    "o-",
                    label=op,
                )
        ax.set_title(title)
        ax.set_xlabel(xlabel)
        ax.set_ylabel("USD / million verified operations")
        ax.set_xticks(sorted({r["topology_point"] for r in selected(points, series)}))
        ax.grid(alpha=0.25)
        ax.legend()
    save(fig, "cost-efficiency")

    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    for op in OPERATIONS:
        rows = selected(points, "medium-concurrency", op)
        for ax, field in zip(
            axes.flat,
            ["verified_tx_s", "p50_ms", "p95_ms", "p99_ms", "failed_terminal_fraction"],
        ):
            ax.plot(
                [r["workers"] for r in rows], [r[field] for r in rows], "o-", label=op
            )
            ax.set_title(field)
            ax.set_xlabel("Workers")
            ax.grid(alpha=0.25)
            ax.legend()
    axes[1, 2].axis("off")
    axes[1, 2].text(
        0,
        0.9,
        "100k-order concurrency series\nREAD32 excluded: no common interval\nDELETE measured at one worker\nFixed-load topology comparisons are separate",
        va="top",
    )
    save(fig, "concurrency")

    with (RESULTS / "concurrency-resources.csv").open() as f:
        resources = list(csv.DictReader(f))
    fields = [
        "app_cpu_percent",
        "db_cpu_percent",
        "db_disk_queue",
        "db_disk_write_bytes_s",
        "buffer_pool_hit_ratio",
        "innodb_row_lock_waits_delta",
    ]
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    for ax, field in zip(axes.flat, fields):
        for op in OPERATIONS:
            rows = [r for r in resources if r["operation"] == op and r[field] != ""]
            ax.plot(
                [int(r["workers"]) for r in rows],
                [float(r[field]) for r in rows],
                "o-",
                label=op,
            )
        ax.set_title(field)
        ax.set_xlabel("Workers")
        ax.grid(alpha=0.25)
        ax.legend()
    axes[1, 1].set_ylim(0, 1.02)
    save(fig, "resources")

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for op in ["CREATE", "UPDATE", "DELETE"]:
        rows = selected(points, "write-targets", op)
        axes[0].plot(
            [r["topology_point"] for r in rows],
            [100 * r["failed_terminal_fraction"] for r in rows],
            "o-",
            label=op,
        )
    axes[0].set_xlabel("Eligible write targets")
    axes[0].set_ylabel("Failed terminals (%)")
    axes[0].set_title("Multi-primary measured failures")
    axes[0].legend()
    contention = selected(points, "contention")
    axes[1].bar(
        ["Single-primary", "Multi-primary"], [r["failed_terminals"] for r in contention]
    )
    axes[1].set_title("Shared-record measured failures")
    axes[1].set_ylabel("Failed terminals")
    for ax in axes:
        ax.grid(axis="y", alpha=0.25)
    save(fig, "conflicts")


def result_document(points):
    text = """# Results

The accepted dataset comprises 58 performance points measured on 4 and 5 October 2026. One medium-fixture 32-worker READ point is excluded because the worker measurement intervals have no common overlap. Different series remain separate observations; they are not pooled repeated trials.

## Application hosts

The application experiment uses 32 total workers, 100k orders and one shared database. Four application hosts achieved 139.966 CREATE/s, 428.980 READ/s, 108.514 UPDATE/s and 150.296 DELETE/s. Timing synchronization and physical host performance limit interpretation of the observed ratios.

"""
    text += matrix(points, "application-scaling")
    text += """

## Read routing

Four application hosts and three single-primary cluster members remain present. Increasing eligible read destinations from one to three increased verified READ throughput from 221.227 to 253.679/s, a ratio of 1.147. Application host CPU was approximately 100%.

"""
    text += matrix(points, "read-targets")
    text += """

## Multi-primary write routing

All three cluster members remain writable and present for quorum. Independently owned orders share immutable master references. Certification failures occur at every configuration and reduce verified goodput.

"""
    text += matrix(points, "write-targets")
    text += """

## Shared-record contention

Thirty-two workers update four shared orders. Single-primary throughput was 89.730 verified updates/s. Multi-primary throughput was 69.852/s, 22.15% lower. The multi-primary common interval contains 29,519 failed terminals: 11,315 certification conflicts, 16,476 native deadlocks and 1,764 commit deadlocks. Measured-operation retries were zero. Exact committed increments were verified on all replicas, with no lost updates in the accepted observations.

Successful multi-primary UPDATE p50/p95/p99 were 84.196/286.948/416.075 ms. These quantiles exclude failed operations. Lower successful latency cannot establish improved aggregate outcomes when failure frequency increases.

## Independent shards

Each shard has one application host, eight workers, 100k orders and 500k baseline lines. The experiment uses weak scaling. All twelve accepted shard points have zero measured errors. Physical node performance varies materially despite matching VM and disk classes.

"""
    text += matrix(points, "shards-weak")
    text += """

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
"""
    return text


def cost_document(points, pricing):
    fleet = pricing["fleet_at_observation"]
    lines = [
        "# Cost analysis",
        "",
        "Costs are public on-demand USD estimates using the captured Frankfurt pricing SKUs. Pricing observations were recorded on 5 October 2026; the retained EU machine-image rate was captured on 4 October 2026. Taxes, credits, contract discounts and currency conversion are excluded.",
        "",
        "## Topology costs",
        "",
        "| Series | Configuration | Applications / databases | Fixed USD/h |",
        "|---|---:|---:|---:|",
    ]
    for series in SERIES:
        for x in sorted({p["topology_point"] for p in selected(points, series)}):
            row = next(p for p in selected(points, series) if p["topology_point"] == x)
            lines.append(
                f"| {SERIES[series][0]} | {x} | {row['application_vms']} / {row['database_vms']} | {row['topology_fixed_usd_hour']:.4f} |"
            )
    lines += [
        "",
        "All three database members are costed in the cluster comparisons. Increasing eligible destinations changes placement without changing member count. Independent sharding increases both application and database host counts.",
        "",
        "Native load generation and Router share application hosts. The estimated topology includes no separate load-generator VM, managed database or paid managed load balancer.",
        "",
        "## Pricing components",
        "",
        "An e2-standard-2 instance costs USD0.08633556/h for compute and USD0.092/h for Windows Server. An 80-GiB standard disk is USD0.005161/h; an 80-GiB balanced disk is USD0.012903/h. Disk and retained-storage hourly normalization uses the captured catalog base-unit conversion of 744 hours per month.",
        "",
        "[Windows Server licensing](https://cloud.google.com/compute/disks-image-pricing#premiumimages) is USD0.046 per visible vCPU/hour. [Cloud NAT](https://cloud.google.com/nat/pricing) adds USD0.0014 per assigned VM/hour, one assumed IP at USD0.005/hour and USD0.045/GiB processed. [VPC pricing](https://cloud.google.com/vpc/network-pricing) provides zero data-transfer charge for the same-zone internal benchmark traffic. External transfer volume is unmeasured.",
        "",
        "The selected [SKU records](../evidence/accepted/pricing.json) retain effective times and unit conversions. MySQL and the user-supplied Delphi CE toolchain contribute no incremental license fee in this model.",
        "",
        "## Unit cost",
        "",
        "| Series | Operation | Lowest observed cost configuration | Operations / USD | USD / million operations |",
        "|---|---|---:|---:|---:|",
    ]
    for series in [
        "application-scaling",
        "read-targets",
        "write-targets",
        "shards-weak",
    ]:
        for op in OPERATIONS:
            rows = selected(points, series, op)
            if rows:
                row = min(rows, key=lambda p: p["usd_per_million_verified_operations"])
                lines.append(
                    f"| {SERIES[series][0]} | {op} | {row['topology_point']} | {row['verified_operations_per_topology_dollar']:,.0f} | {row['usd_per_million_verified_operations']:.3f} |"
                )
    lines += [
        "",
        "Within the fixed-worker application series, two application hosts have the lowest observed CREATE, UPDATE and DELETE unit costs; four hosts have the lowest READ unit cost. Three eligible destinations have the lowest observed unit costs in the fixed-size cluster series. Four shards have the lowest observed unit costs in the weak-scaling series.",
        "",
        "These comparisons apply within each series. Workload semantics, synchronization, replication and physical node performance prevent a general production recommendation. Successful operation cost does not account for the application consequences of failed requests.",
        "",
        "[Cost-efficiency figure](../results/figures/cost-efficiency.png) and [complete cost table](../results/measurements.csv) include normalized operations per hour, operations per dollar and incremental throughput per incremental dollar. Incremental efficiency is undefined when topology cost is unchanged.",
        "",
        "## Infrastructure observation",
        "",
        f"The pre-deletion fleet comprised nine VMs: four application hosts, four database hosts and one SDK coordinator. Their compute, Windows, disk and fixed NAT estimate was USD{fleet['topology_fixed_usd_hour']:.4f}/h. Including known retained storage, the estimate was USD{fleet['known_fixed_usd_hour']:.4f}/h or USD{fleet['known_fixed_usd_day']:.2f}/day. This fleet estimate includes inactive experiment hosts and is separate from the active-topology comparisons.",
        "",
        "The [timestamped infrastructure receipt](../evidence/accepted/infrastructure.json) records zero instances, attached disks, NAT routers, reserved addresses and forwarding rules. This receipt is a historical observation, not a live resource inventory.",
        "",
        f"Three machine images and the database snapshot estimate USD{fleet['retained_images_snapshot_usd_month']:.2f}/month. The retained artifact bucket estimates USD{fleet['gcs_versions_storage_usd_month_excluding_soft_deleted']:.2f}/month at the captured size. Combined retained storage is approximately USD{fleet['retained_images_snapshot_usd_month'] + fleet['gcs_versions_storage_usd_month_excluding_soft_deleted']:.2f}/month. Metadata, storage operations, logging and variable transfer are excluded.",
        "",
        "## Billing limitations",
        "",
        "Actual cumulative project spend is unavailable from the measurement receipts. Creation timestamps do not reconstruct stopped intervals, other deleted environments, failed setup attempts, transfers or credits. Reconciliation requires a Cloud Billing usage export or invoice. No cumulative billed total is inferred.",
    ]
    return "\n".join(lines) + "\n"


def main():
    measurements = read(ACCEPTED / "measurements.json")
    pricing = read(ACCEPTED / "pricing.json")
    points = measurements["points"]
    if len(points) != 58:
        raise ValueError("Expected 58 accepted configurations")
    FIGURES.mkdir(parents=True, exist_ok=True)
    with (RESULTS / "measurements.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(points[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(points)
    figures(points)
    (ROOT / "docs/results.md").write_text(result_document(points))
    (ROOT / "docs/cost-analysis.md").write_text(cost_document(points, pricing))
    print(
        json.dumps(
            {"accepted_points": len(points), "figures": 6, "cloud_operations": 0}
        )
    )


if __name__ == "__main__":
    main()
