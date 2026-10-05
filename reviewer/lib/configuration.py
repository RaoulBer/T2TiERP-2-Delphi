from dataclasses import asdict, dataclass
from ipaddress import ip_network
from pathlib import Path
import re

from .errors import require
from .files import read
from .paths import ROOT


@dataclass(frozen=True)
class Cell:
    topology_point: int
    operation: str
    application_vms: int
    database_vms: int
    workers: int
    orders: int

    def __post_init__(self):
        for name in (
            "topology_point",
            "application_vms",
            "database_vms",
            "workers",
            "orders",
        ):
            require(type(getattr(self, name)) is int and getattr(self, name) > 0, name)
        require(self.operation in {"CREATE", "READ", "UPDATE", "DELETE"}, "OPERATION")
        require(self.application_vms in {1, 2, 4}, "APPLICATION_COUNT")
        require(self.database_vms in {1, 2, 3, 4}, "DATABASE_COUNT")
        require(self.workers % self.application_vms == 0, "WORKER_ALLOCATION")


def load_config(path):
    config = read(path)
    keys = (
        "project_id",
        "zone",
        "region",
        "prefix",
        "bucket_name",
        "windows_image",
        "native_inputs",
        "dependency_inputs",
        "private_cidr",
    )
    for key in keys:
        require(isinstance(config.get(key), str) and bool(config[key]), "CONFIG_" + key)
    require(re.fullmatch(r"[a-z][a-z0-9-]{2,21}", config["prefix"]), "RESOURCE_PREFIX")
    require(config["zone"].startswith(config["region"] + "-"), "ZONE_REGION")
    network = ip_network(config["private_cidr"], strict=True)
    private_ranges = [
        ip_network(c) for c in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
    ]
    require(network.version == 4 and network.prefixlen == 24, "PRIVATE_SUBNET_SIZE")
    require(any(network.subnet_of(n) for n in private_ranges), "PRIVATE_SUBNET_ADDRESS")
    require(
        re.fullmatch(
            r"projects/[^/]+/global/images/(?:family/)?[^/]+", config["windows_image"]
        ),
        "IMAGE_PATH",
    )
    for key in ("native_inputs", "dependency_inputs"):
        config[key] = str((ROOT / config[key]).resolve())
    return config


def configuration(series, point, operation):
    require(re.fullmatch(r"[a-z-]+", series), "EXPERIMENT_NAME")
    spec = read(ROOT / "experiments" / (series + ".json"))
    selected = [
        c
        for c in spec["configurations"]
        if str(c["topology_point"]) == str(point) and c["operation"] == operation
    ]
    require(len(selected) == 1, "CONFIGURATION_NOT_RECORDED")
    cell = Cell(**selected[0])
    return spec, asdict(cell)
