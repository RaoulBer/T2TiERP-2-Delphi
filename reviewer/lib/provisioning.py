import json
import os
import subprocess

from .errors import require
from .files import read, write
from .paths import ROOT

VARIABLES = {
    "storage": ("project_id", "region", "prefix", "bucket_name"),
    "workload": (
        "project_id",
        "region",
        "zone",
        "prefix",
        "bucket_name",
        "private_cidr",
        "windows_image",
        "application_count",
        "database_count",
        "application_disk_type",
    ),
}


def execute(directory, stack, arguments, capture=False):
    source = ROOT / "infrastructure" / stack
    environment = dict(os.environ)
    environment["TF_DATA_DIR"] = str(directory / "terraform" / stack / "providers")
    return subprocess.run(
        ["terraform", "-chdir=" + str(source), *arguments],
        cwd=ROOT,
        env=environment,
        check=True,
        timeout=1800,
        stdout=subprocess.PIPE if capture else None,
        text=True,
    ).stdout


def variables(directory, stack, state):
    values = read(directory / "terraform.tfvars.json")
    subset = {key: values[key] for key in VARIABLES[stack]}
    if stack == "workload":
        subset["runtime_service_account"] = state.get("storage", {}).get(
            "runtime_service_account", ""
        )
    target = directory / "terraform" / stack / "variables.json"
    write(target, subset)
    return target


def outputs(directory, stack):
    output = execute(
        directory,
        stack,
        [
            "output",
            "-state=" + str(directory / "terraform" / stack / "state.tfstate"),
            "-json",
        ],
        capture=True,
    )
    return {key: value["value"] for key, value in json.loads(output).items()}


def terraform(directory, action):
    state = read(directory / "run.json")
    if action == "destroy":
        stack = "workload"
        values = variables(directory, stack, state)
        execute(directory, stack, ["init", "-input=false"])
        execute(
            directory,
            stack,
            [
                "destroy",
                "-input=false",
                "-auto-approve",
                "-state=" + str(directory / "terraform" / stack / "state.tfstate"),
                "-var-file=" + str(values),
            ],
        )
        state["status"] = "COMPUTE_DESTROYED_STORAGE_RETAINED"
        write(directory / "run.json", state)
        return
    stack = "workload" if "storage" in state else "storage"
    values = variables(directory, stack, state)
    execute(directory, stack, ["init", "-input=false"])
    plan = directory / "terraform" / stack / "plan.tfplan"
    if action == "plan":
        execute(
            directory,
            stack,
            [
                "plan",
                "-input=false",
                "-state=" + str(directory / "terraform" / stack / "state.tfstate"),
                "-var-file=" + str(values),
                "-out=" + str(plan),
            ],
        )
        state["planned_stack"] = stack
        write(directory / "run.json", state)
        print(json.dumps({"planned_stack": stack, "plan": str(plan)}))
        return
    require(
        action == "apply" and state.get("planned_stack") == stack and plan.is_file(),
        "SAVED_PLAN_REQUIRED",
    )
    execute(directory, stack, ["apply", "-input=false", str(plan)])
    resolved = outputs(directory, stack)
    if stack == "storage":
        state["storage"] = resolved
        state["status"] = "STORAGE_PROVISIONED"
    else:
        state["infrastructure"] = resolved
        state["status"] = "PROVISIONED"
    state.pop("planned_stack", None)
    write(directory / "run.json", state)
    print(json.dumps({"applied_stack": stack, "status": state["status"]}))
