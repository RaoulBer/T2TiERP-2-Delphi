import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT)


def main():
    manifest = json.loads((ROOT / "benchmark/source-manifest.json").read_text())
    base = manifest["upstream_commit"]
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", base, "HEAD"], cwd=ROOT, check=True
    )
    algorithm = git("rev-parse", "--show-object-format").decode().strip()
    original = {}
    for record in git("ls-tree", "-r", "-z", base).split(b"\0"):
        if not record:
            continue
        metadata, name = record.split(b"\t", 1)
        mode, kind, object_id = metadata.split()
        if kind != b"blob":
            raise ValueError("Unsupported upstream object type")
        original[os.fsdecode(name)] = (mode.decode(), object_id.decode())
    changed = []
    missing = []
    for name, (mode, expected) in original.items():
        path = ROOT / name
        if not path.is_file():
            missing.append(name)
            continue
        content = (
            os.fsencode(os.readlink(path)) if mode == "120000" else path.read_bytes()
        )
        digest = hashlib.new(
            algorithm, b"blob " + str(len(content)).encode() + b"\0" + content
        ).hexdigest()
        if digest != expected:
            changed.append(name)
    if missing or sorted(changed) != sorted(manifest["modified_upstream_paths"]):
        raise ValueError(
            json.dumps(
                {"missing_upstream_files": missing, "modified_upstream_files": changed}
            )
        )
    units = 0
    for name in manifest["files"]:
        if not name.startswith("benchmark/source/Retaguarda/"):
            continue
        source = name.removeprefix("benchmark/source/")
        if (ROOT / name).read_bytes() != (ROOT / source).read_bytes():
            raise ValueError("Retained ERP source differs: " + source)
        units += 1
    if units != 28:
        raise ValueError("Expected 28 retained original ERP dependency units")
    print(
        json.dumps(
            {
                "status": "PASS",
                "base_commit": base,
                "upstream_files": len(original),
                "unchanged_upstream_files": len(original) - len(changed),
                "modified_upstream_paths": changed,
                "identical_erp_units": units,
                "cloud_operations": 0,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
