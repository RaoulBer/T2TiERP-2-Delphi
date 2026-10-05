import hashlib
import json
import re
from pathlib import Path

from lib.configuration import configuration
from lib.errors import require
from lib.paths import ROOT


def main():
    manifest = json.loads((ROOT / "benchmark/source-manifest.json").read_text())
    for name, expected in manifest["files"].items():
        path = ROOT / name
        require(path.is_file(), name)
        require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, name)
    accepted = json.loads((ROOT / "evidence/accepted/measurements.json").read_text())[
        "points"
    ]
    expected = {(p["series"], p["topology_point"], p["operation"]): p for p in accepted}
    observed = set()
    for path in sorted((ROOT / "experiments").glob("*.json")):
        spec = json.loads(path.read_text())
        phases = (
            spec["warmup_seconds"],
            spec["measurement_seconds"],
            spec["cooldown_seconds"],
        )
        require(
            phases == (60, 180, 30) and spec["trials_per_configuration"] == 1,
            "MEASUREMENT_PHASES",
        )
        for cell in spec["configurations"]:
            key = spec["name"], cell["topology_point"], cell["operation"]
            require(key in expected and key not in observed, "CONFIGURATION_COVERAGE")
            require(
                all(expected[key][k] == v for k, v in cell.items()),
                "CONFIGURATION_VALUES",
            )
            require(configuration(*key)[1] == cell, "CONFIGURATION_SELECTION")
            observed.add(key)
    require(
        observed == set(expected) and len(observed) == 58, "RECORDED_CONFIGURATIONS"
    )
    for folder in ["reviewer", "infrastructure", "benchmark/runtime"]:
        for path in (ROOT / folder).rglob("*"):
            if (
                "runs" in path.parts
                or "inputs" in path.parts
                or "__pycache__" in path.parts
                or path == Path(__file__).resolve()
                or not path.is_file()
                or path.suffix not in [".py", ".ps1", ".tf", ".js"]
            ):
                continue
            text = path.read_text()
            require(".local/T2Ti" not in text, str(path))
            require(
                not re.search(r"\bws-[A-Za-z0-9]{12,}\b", text),
                "PRIVATE_WORKSPACE_REFERENCE",
            )
    print(
        json.dumps(
            {
                "status": "PASS",
                "source_files": len(manifest["files"]),
                "recorded_configurations": len(observed),
                "cloud_actions": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
