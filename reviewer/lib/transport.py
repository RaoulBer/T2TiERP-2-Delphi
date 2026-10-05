from pathlib import Path
import json
import subprocess
import time
import uuid
from .paths import ROOT, RUNTIME
from .files import read, write, sha, command, utc_after


class Transport:
    def __init__(self, directory):
        self.directory = directory
        self.s = read(directory / "run.json")
        self.c = self.s["config"]
        self.hosts = self.s["infrastructure"]["hosts"]
        self.bucket = self.s["infrastructure"]["bucket"]

    def upload(self, path, object_):
        command(
            [
                "gcloud",
                "storage",
                "cp",
                path,
                "gs://" + self.bucket + "/" + object_,
                "--quiet",
            ],
            capture=True,
        )
        return {"name": Path(path).name, "object": object_, "sha256": sha(path)}

    def asset(self, path, name=None):
        a = self.upload(
            path,
            "inputs/"
            + self.s["id"]
            + "/"
            + sha(path)
            + "/"
            + (name or Path(path).name),
        )
        if name:
            a["name"] = name
        return a

    def fetch(self, phase, name):
        url = "gs://" + self.bucket + "/results/" + phase + "/benchmark/" + name
        p = subprocess.run(
            ["gcloud", "storage", "cat", url, "--quiet"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
        if p.returncode:
            if (
                "404" in p.stderr
                or "matched no objects" in p.stderr
                or "No URLs matched" in p.stderr
            ):
                return None
            raise RuntimeError(
                "GCS read failed; verify account permissions and connectivity"
            )
        return json.loads(p.stdout)

    def wait(self, phase, names, status, timeout=2400):
        deadline = time.monotonic() + timeout
        remaining = set(names)
        while remaining and time.monotonic() < deadline:
            for name in list(remaining):
                receipt = self.fetch(phase, name)
                if receipt:
                    if receipt.get("status") == "FAILED":
                        raise RuntimeError(name + ": " + str(receipt.get("failure")))
                    if receipt.get("status") in status:
                        remaining.remove(name)
            if remaining:
                time.sleep(3)
        if remaining:
            raise TimeoutError(
                "Missing completed receipts: " + ", ".join(sorted(remaining))
            )

    def dispatch(self, role, phase, script, payload, assets=()):
        script_path = RUNTIME / script
        common = self.asset(RUNTIME / "common.ps1")
        script_asset = self.asset(script_path)
        files = [common, script_asset, *assets]
        m = {
            "bucket": self.bucket,
            "phase": phase,
            "role": role,
            "instance_id": self.hosts[role]["id"],
            "assets": list(assets),
            **payload,
        }
        job = {
            "id": uuid.uuid4().hex,
            "deadline_utc": utc_after(7200),
            "work_directory": "app" if role.startswith("app-") else "db",
            "script": script,
            "files": files,
            "manifest": m,
        }
        local = self.directory / "jobs" / (job["id"] + ".json")
        write(local, job)
        self.upload(local, "jobs/" + role + "/latest.json")

    def dependencies(self, names):
        lock = read(ROOT / "benchmark/dependencies.json")["files"]
        assets = []
        for name in names:
            path = Path(self.c["dependency_inputs"]) / name
            if not path.is_file() or sha(path) != lock[name]["sha256"]:
                raise ValueError("Supply the pinned dependency: " + name)
            assets.append(self.asset(path))
        return assets

    def credentials(self):
        return self.asset(self.directory / "credentials.json")
