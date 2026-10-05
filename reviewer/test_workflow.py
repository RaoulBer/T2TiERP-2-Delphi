import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from lib import fixtures, provisioning
from lib.configuration import Cell, configuration, load_config
from lib.errors import VerificationError
from lib.files import read, sha, write
from lib.paths import AUTHOR, ROOT


class ConfigurationTests(unittest.TestCase):
    def test_unexecuted_configuration_is_rejected(self):
        for series, point, operation in [
            ("medium-concurrency", 32, "READ"),
            ("medium-concurrency", 16, "DELETE"),
            ("read-targets", 4, "READ"),
        ]:
            with self.subTest(series=series, point=point), self.assertRaises(
                ValueError
            ):
                configuration(series, point, operation)

    def test_customer_ownership_uses_per_shard_population(self):
        spec, cell = configuration("shards-weak", 4, "CREATE")
        self.assertEqual(cell["orders"], 400000)
        self.assertEqual(spec["orders_per_node"] * cell["database_vms"], cell["orders"])

    def test_fixture_generation_is_local(self):
        spec, cell = configuration("small-create", 1, "CREATE")
        config = load_config(ROOT / "reviewer/config.example.json")
        with tempfile.TemporaryDirectory() as temp, patch.object(
            fixtures, "RUNS", Path(temp)
        ), patch("subprocess.run", side_effect=AssertionError("External execution")):
            directory = fixtures.prepare_local(config, spec, cell)
            state = read(directory / "run.json")
            manifest = state["fixtures"]["db-1"]
            self.assertEqual(manifest["population_sales"], 10000)
            self.assertEqual(manifest["population_details"], 50000)
            self.assertEqual(len(manifest["expected_table_rows"]), 40)
            self.assertEqual(
                sha(directory / "fixtures/db-1/dataset.sql"),
                manifest["dataset_sql_sha256"],
            )
            self.assertEqual(state["configuration"], cell)
            self.assertEqual(
                (directory / "credentials.json").stat().st_mode & 0o777, 0o600
            )

    def test_corrupt_fixture_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            schema = Path(temp) / "schema.sql"
            schema.write_bytes(
                (AUTHOR / "schema.sql").read_bytes() + b"\n-- alteration\n"
            )
            with self.assertRaises(ValueError):
                fixtures.inputs(
                    AUTHOR / "model.xml",
                    AUTHOR / "export-receipt.json",
                    schema,
                    AUTHOR / "views.sql",
                )

    def test_validation_survives_optimized_python(self):
        result = subprocess.run(
            [
                sys.executable,
                "-O",
                "-c",
                "from lib.errors import require; require(False, 'INVALID_OBSERVATION')",
            ],
            cwd=ROOT / "reviewer",
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("VerificationError: INVALID_OBSERVATION", result.stderr)

    def test_inconsistent_worker_allocation_is_rejected(self):
        with self.assertRaises(VerificationError):
            Cell(4, "READ", 4, 1, 7, 100000)

    def test_invalid_network_and_prefix_are_rejected(self):
        original = read(ROOT / "reviewer/config.example.json")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            for key, value in [
                ("private_cidr", "8.8.8.0/24"),
                ("private_cidr", "10.0.0.0/16"),
                ("prefix", "A" * 40),
            ]:
                write(path, {**original, key: value})
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    load_config(path)


class WorkloadTests(unittest.TestCase):
    def test_baseline_and_synchronized_read_semantics(self):
        from lib.workloads import worker_profile

        spec, cell = configuration("small-other-crud", 4, "READ")
        baseline = worker_profile(spec, cell)
        self.assertEqual(baseline["worker_executable"], "SalePerformance.exe")
        self.assertFalse(baseline["synchronized"])
        spec, cell = configuration("shards-weak", 4, "READ")
        owned = worker_profile(spec, cell)
        self.assertEqual(owned["worker_executable"], "SaleSynchronizedPerformance.exe")
        self.assertTrue(owned["synchronized"])
        spec, cell = configuration("read-targets", 3, "READ")
        existing = worker_profile(spec, cell)
        self.assertEqual(
            existing["worker_executable"], "SaleInquirySynchronizedPerformance.exe"
        )
        self.assertEqual(existing["route_kind"], "read")
        self.assertEqual(existing["launch_stagger_ms"], 200)

    def test_shared_and_independent_write_ownership(self):
        from lib.workloads import worker_profile

        spec, cell = configuration("contention", 3, "UPDATE")
        shared = worker_profile(spec, cell)
        self.assertEqual(shared["worker_executable"], "SaleSharedContention.exe")
        self.assertEqual(shared["shared_pool_size"], 4)
        spec, cell = configuration("write-targets", 3, "UPDATE")
        independent = worker_profile(spec, cell)
        self.assertEqual(
            independent["worker_executable"], "SaleConflictPerformance.exe"
        )
        self.assertEqual(independent["shared_pool_size"], 0)
        self.assertEqual(independent["route_kind"], "write")


class SummaryTests(unittest.TestCase):
    def summarize(self, directory, offset):
        from summarize import run

        run_id = "test"
        packet = {
            "cells": [
                {
                    "run_id": run_id,
                    "operation": "SALE_READ",
                    "workers": 2,
                    "worker_ids": [offset, offset + 1],
                }
            ],
            "cell_hosts": {run_id: {"app-2": {"workers": 2, "worker_offset": offset}}},
            "hosts": {"app-2": {"id": "123"}},
            "worker_exe_sha256": "fixture",
            "dataset_orders": 100000,
            "dataset_lines": 500000,
            "app_hosts": 1,
            "database_roles": ["db-2"],
            "disk_description": "fixture",
            "read_semantics": "owned aggregate",
        }
        actual = directory / "actual"
        actual.mkdir()
        workers = []
        for i in range(2):
            worker = offset + i
            identity = {
                "run_id": run_id,
                "worker_id": worker,
                "instance_id": "123",
                "exe_sha256": "fixture",
            }
            common = {"identity": identity, "phase": "MEASUREMENT"}
            events = [
                {
                    **common,
                    "event": "phase_started",
                    "observed_utc": "2026-10-05T00:00:00Z",
                },
                {
                    **common,
                    "event": "attempt_started",
                    "global_attempt_id": str(worker),
                    "observed_utc": "2026-10-05T00:00:10Z",
                },
                {
                    **common,
                    "event": "attempt_terminal",
                    "global_attempt_id": str(worker),
                    "observed_utc": "2026-10-05T00:00:11Z",
                    "outcome": "COMPLETED_PENDING_INDEPENDENT_OBSERVER",
                    "duration_qpc_ticks": 10 + 20 * i,
                    "qpc_frequency": 1000,
                },
                {
                    **common,
                    "event": "phase_terminal",
                    "observed_utc": "2026-10-05T00:03:00Z",
                },
                {**common, "event": "worker_finished"},
            ]
            path = actual / f"{run_id}-{worker}.ndjson"
            path.write_text("".join(json.dumps(e) + "\n" for e in events))
            workers.append({"exit_code": 0, "output_sha256": sha(path)})
        write(
            actual / f"{run_id}-app-2-receipt.json",
            {"role": "app-2", "instance_id": "123", "workers": workers},
        )
        write(directory / "packet.json", packet)
        run(directory)
        return read(directory / "results.json")["cells"][0]

    def test_nonzero_worker_offsets_preserve_statistics(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            zero = self.summarize(Path(first), 0)
            offset = self.summarize(Path(second), 8)
            self.assertEqual(zero, offset)
            self.assertTrue(offset["execution_complete"])
            window = offset["concurrency_aligned"]
            self.assertEqual(window["successful_completions"], 2)
            self.assertEqual(window["seconds"], 180)
            self.assertEqual(window["latency_ms"], {"p50": 20, "p95": 29, "p99": 29.8})


class ProvisioningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        config = read(ROOT / "reviewer/config.example.json")
        config.update(
            application_count=4, database_count=3, application_disk_type="pd-standard"
        )
        write(self.directory / "terraform.tfvars.json", config)
        write(
            self.directory / "run.json",
            {"id": "test", "status": "LOCAL_INPUTS_PREPARED"},
        )

    def tearDown(self):
        self.temp.cleanup()

    def execute(self, directory, stack, args, capture=False):
        if args[0] == "plan":
            (directory / "terraform" / stack / "plan.tfplan").write_bytes(b"plan")
        if args[0] == "output":
            values = (
                {
                    "runtime_service_account": "runtime@example.invalid",
                    "bucket": "example",
                }
                if stack == "storage"
                else {"hosts": {}, "bucket": "example"}
            )
            return json.dumps({key: {"value": value} for key, value in values.items()})

    def test_storage_then_workload_saved_plans(self):
        with patch.object(provisioning, "execute", side_effect=self.execute) as execute:
            for _ in range(2):
                provisioning.terraform(self.directory, "plan")
                provisioning.terraform(self.directory, "apply")
            self.assertEqual(
                [
                    call.args[1]
                    for call in execute.call_args_list
                    if call.args[2][0] == "apply"
                ],
                ["storage", "workload"],
            )
            state = read(self.directory / "run.json")
            self.assertEqual(state["status"], "PROVISIONED")
            self.assertIn("storage", state)
            self.assertIn("infrastructure", state)
            self.assertEqual(
                read(self.directory / "terraform/workload/variables.json")[
                    "runtime_service_account"
                ],
                state["storage"]["runtime_service_account"],
            )

    def test_apply_without_saved_plan_is_rejected(self):
        with patch.object(provisioning, "execute") as execute, self.assertRaises(
            VerificationError
        ):
            provisioning.terraform(self.directory, "apply")
        self.assertFalse(
            any(call.args[2][0] == "apply" for call in execute.call_args_list)
        )

    def test_destroy_retains_storage_without_targeting(self):
        state = read(self.directory / "run.json")
        state["storage"] = {"runtime_service_account": "runtime@example.invalid"}
        write(self.directory / "run.json", state)
        with patch.object(provisioning, "execute") as execute:
            provisioning.terraform(self.directory, "destroy")
        self.assertEqual(
            [call.args[1] for call in execute.call_args_list], ["workload", "workload"]
        )
        arguments = execute.call_args_list[-1].args[2]
        self.assertEqual(arguments[0], "destroy")
        self.assertFalse(any("-target" in arg for arg in arguments))
        self.assertEqual(read(self.directory / "run.json")["storage"], state["storage"])

    def test_provider_directory_is_run_and_stack_local(self):
        with patch("subprocess.run") as run:
            provisioning.execute(self.directory, "storage", ["validate"])
        self.assertEqual(
            run.call_args.kwargs["env"]["TF_DATA_DIR"],
            str(self.directory / "terraform/storage/providers"),
        )
        self.assertEqual(run.call_args.kwargs["timeout"], 1800)


if __name__ == "__main__":
    unittest.main()
