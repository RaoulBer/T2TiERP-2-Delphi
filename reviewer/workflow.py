import argparse
import json
from pathlib import Path

from lib.paths import ROOT, RUNS
from lib.configuration import configuration, load_config
from lib.fixtures import prepare_local
from lib.transport import Transport
from lib.provisioning import terraform
from lib.execution import initialize_database, measure, collect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=[
            "configure",
            "plan",
            "apply",
            "prepare",
            "measure",
            "collect",
            "verify",
            "destroy",
        ],
    )
    parser.add_argument("--config", default=str(ROOT / "reviewer/config.json"))
    parser.add_argument("--series")
    parser.add_argument("--point")
    parser.add_argument("--operation", choices=["CREATE", "READ", "UPDATE", "DELETE"])
    parser.add_argument("--run")
    a = parser.parse_args()
    if a.action == "configure":
        if not all([a.series, a.point, a.operation]):
            parser.error("configure requires --series, --point and --operation")
        spec, p = configuration(a.series, a.point, a.operation)
        directory = prepare_local(load_config(a.config), spec, p)
        print(
            json.dumps(
                {
                    "status": "LOCAL_INPUTS_PREPARED",
                    "run": str(directory),
                    "cloud_actions": 0,
                }
            )
        )
        return
    if not a.run:
        parser.error("--run is required")
    directory = Path(a.run).resolve()
    if directory.parent != RUNS.resolve():
        raise ValueError("Run must be under reviewer/runs")
    if a.action in ["plan", "apply", "destroy"]:
        terraform(directory, a.action)
    elif a.action == "verify":
        from verify_run import verify

        print(json.dumps(verify(directory), indent=2))
    else:
        t = Transport(directory)
        {"prepare": initialize_database, "measure": measure, "collect": collect}[
            a.action
        ](t)


if __name__ == "__main__":
    main()
