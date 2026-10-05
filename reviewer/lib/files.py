from pathlib import Path
import datetime
import hashlib
import json
import subprocess
from .paths import ROOT


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2) + "\n")


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def command(args, capture=False, timeout=1800):
    return subprocess.run(
        [str(x) for x in args],
        cwd=ROOT,
        check=True,
        timeout=timeout,
        stdout=subprocess.PIPE if capture else None,
        text=True,
    ).stdout


def utc_after(seconds):
    return (
        datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(seconds=seconds)
    ).isoformat()
