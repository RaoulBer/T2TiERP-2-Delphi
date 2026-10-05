"""Validate active research data, local preservation and repository exclusions."""

import csv
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    errors = []

    def require(condition, message):
        if not condition:
            errors.append(message)

    accepted = ROOT / "evidence/accepted"
    measurements = read(accepted / "measurements.json")
    points = measurements["points"]
    require(len(points) == 58, "Expected 58 accepted points")
    require(
        len(measurements["excluded_points"]) == 1, "Expected one excluded READ point"
    )
    for p in points:
        require(
            math.isclose(
                p["verified_operations_per_topology_dollar"],
                3600 * p["verified_tx_s"] / p["topology_fixed_usd_hour"],
            ),
            "Unit-cost inconsistency",
        )
        require(
            math.isclose(
                p["usd_per_million_verified_operations"]
                * p["verified_operations_per_topology_dollar"],
                1e6,
            ),
            "Inverse unit-cost inconsistency",
        )
        require(
            math.isclose(
                sum(
                    p[k]
                    for k in [
                        "compute_usd_hour",
                        "windows_usd_hour",
                        "disk_usd_hour",
                        "nat_fixed_usd_hour",
                    ]
                ),
                p["topology_fixed_usd_hour"],
            ),
            "Hourly cost components disagree",
        )
    cluster_costs = {
        p["topology_fixed_usd_hour"]
        for p in points
        if p["series"] in ["read-targets", "write-targets", "contention"]
    }
    require(
        len(cluster_costs) == 1, "Cluster cost must retain three members at every point"
    )
    for series, count in [
        ("application-scaling", 12),
        ("read-targets", 3),
        ("write-targets", 9),
        ("contention", 2),
        ("shards-weak", 12),
        ("medium-concurrency", 12),
    ]:
        require(
            sum(p["series"] == series for p in points) == count,
            f"Point count differs: {series}",
        )
    with (ROOT / "results/measurements.csv").open() as f:
        csv_rows = list(csv.DictReader(f))
    require(len(csv_rows) == len(points), "Derived CSV point count differs")
    for row, point in zip(csv_rows, points):
        require(
            all(
                row[k] == ("" if value is None else str(value))
                for k, value in point.items()
            ),
            "Derived CSV differs from accepted data",
        )

    docs = [ROOT / name for name in ["README.md", "PROMPT.md", "TASKS.md"]] + sorted(
        (ROOT / "docs").glob("*.md")
    )
    for path in docs:
        text = path.read_text()
        require("\u2014" not in text, f"Em dash in {path.name}")
        require(
            not re.search(r"^Version\s*:", text, re.I | re.M),
            f"Manual version header in {path.name}",
        )
        require(
            not re.search(r"\bv\d+\b", path.stem, re.I),
            f"Revision suffix in {path.name}",
        )
        prose = re.sub(r"```.*?```", "", text, flags=re.S)
        require(
            not re.search(
                r"\b(?:I|we) (?:will|have|did|implemented|ran)|\b(?:delve|leverage|journey|game.changer)\b|bottom line|it's worth noting",
                prose,
                re.I,
            ),
            f"Narrative or promotional language in {path.name}",
        )
        for target in re.findall(r"\]\(([^)]+)\)", text):
            if target.startswith(("https://", "http://", "#")):
                continue
            require(
                (path.parent / target.split("#", 1)[0]).exists(),
                f"Broken link in {path.name}: {target}",
            )

    receipt = read(ROOT / "evidence/reproducibility.json")
    for key, relative in [
        ("source_manifest_sha256", "benchmark/source-manifest.json"),
        ("dependency_manifest_sha256", "benchmark/dependencies.json"),
    ]:
        require(
            receipt[key] == digest(ROOT / relative),
            f"Validation receipt input differs: {relative}",
        )

    provenance = read(accepted / "provenance.json")
    checked = 0
    for item in provenance["files"] + provenance["raw_sources"]:
        relative = item.get("file", item.get("path"))
        path = ROOT / relative
        if path.exists():
            require(
                digest(path) == item["sha256"],
                f"Provenance checksum differs: {relative}",
            )
            checked += 1
        elif relative.startswith(("evidence/", ".archive/")):
            require(
                relative.startswith(".archive/") and not (ROOT / ".archive").exists(),
                f"Missing local evidence: {relative}",
            )

    manifest = ROOT / ".archive/manifest.json"
    preserved = 0
    if manifest.exists():
        for item in read(manifest)["records"]:
            path = ROOT / item["archive_path"]
            require(
                path.is_file() and digest(path) == item["sha256"],
                f'Archived bytes differ: {item["original_path"]}',
            )
            preserved += 1

    additional_preserved = 0
    for archive_manifest in [
        ROOT / ".archive/reproducibility-documents/manifest.json",
        ROOT / ".archive/replay-unused-runtime/manifest.json",
        ROOT / ".archive/replay-unreferenced-source/manifest.json",
        ROOT / ".archive/scientific-cleanup/manifest.json",
        ROOT / ".archive/fork-transition/manifest.json",
    ]:
        if archive_manifest.exists():
            for item in read(archive_manifest)["records"]:
                path = ROOT / item["archive_path"]
                require(
                    path.is_file() and digest(path) == item["sha256"],
                    f'Additional archive bytes differ: {item["original_path"]}',
                )
                additional_preserved += 1

    tracked_private = subprocess.check_output(
        ["git", "ls-files", ".archive", ".local", "blueprints"], cwd=ROOT, text=True
    ).strip()
    require(not tracked_private, "Private archive or runtime inputs are tracked")
    for relative in [
        ".archive/manifest.json",
        ".local/inputs/delphi/installer.exe",
        "blueprints/",
    ]:
        result = subprocess.run(["git", "check-ignore", "-q", relative], cwd=ROOT)
        require(result.returncode == 0, f"Private path is not ignored: {relative}")
    infrastructure = read(accepted / "infrastructure.json")
    for key in [
        "remaining_instances",
        "remaining_disks",
        "remaining_routers",
        "remaining_addresses",
        "remaining_forwarding_rules",
    ]:
        require(infrastructure[key] == [], f"Teardown observation is not empty: {key}")
    print(
        json.dumps(
            {
                "status": "PASS" if not errors else "FAIL",
                "accepted_points": len(points),
                "archived_files_verified": preserved,
                "additional_archived_files_verified": additional_preserved,
                "provenance_files_verified": checked,
                "errors": errors,
            },
            indent=2,
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
