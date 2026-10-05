import gzip
import secrets
import shutil
import uuid
from .paths import RUNS, AUTHOR
from .files import write
from .fixture_inputs import Dataset, CustomerPartition, inputs


def prepare_local(c, spec, p):
    run = uuid.uuid4().hex
    directory = RUNS / run
    directory.mkdir(parents=True)
    credentials = {
        "root_password": secrets.token_hex(24),
        "app_password": secrets.token_hex(24),
    }
    write(directory / "credentials.json", credentials)
    (directory / "credentials.json").chmod(0o600)
    node_count = p["database_vms"] if spec["name"] == "shards-weak" else 1
    receipt, base, order = inputs(
        AUTHOR / "model.xml",
        AUTHOR / "export-receipt.json",
        AUTHOR / "schema.sql",
        AUTHOR / "views.sql",
    )
    manifests = {}
    for i in range(node_count):
        destination = directory / "fixtures" / ("db-" + str(i + 1))
        args = (
            receipt,
            base,
            order,
            spec["orders_per_node"] if spec["name"] == "shards-weak" else p["orders"],
            run,
            spec["fixture_seed"],
            8 if spec["name"] == "shards-weak" else p["workers"],
            100000,
        )
        generator = (
            CustomerPartition(*args, shard_index=i)
            if spec["name"] == "shards-weak"
            else Dataset(*args)
        )
        manifests["db-" + str(i + 1)] = generator.generate(destination)
        with (destination / "dataset.sql").open("rb") as source, (
            destination / "dataset.sql.gz"
        ).open("wb") as target:
            with gzip.GzipFile(
                filename="", fileobj=target, mode="wb", mtime=0
            ) as zipped:
                shutil.copyfileobj(source, zipped)
    vars_ = {
        k: c[k]
        for k in [
            "project_id",
            "region",
            "zone",
            "prefix",
            "bucket_name",
            "windows_image",
            "private_cidr",
        ]
    }
    vars_.update(
        application_count=p["application_vms"],
        database_count=p["database_vms"],
        application_disk_type=spec["application_disk_type"],
    )
    write(directory / "terraform.tfvars.json", vars_)
    state = {
        "id": run,
        "config": c,
        "experiment": spec,
        "configuration": p,
        "fixtures": manifests,
        "status": "LOCAL_INPUTS_PREPARED",
    }
    write(directory / "run.json", state)
    return directory
