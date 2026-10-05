# Reproducibility

## Source ancestry

The working branch descends from the original T2Ti ERP commit identified in [the source manifest](../benchmark/source-manifest.json). The full application source is retained at its original paths. The root README describes the measured research scope; the original README remains available at the pinned upstream commit. Native worker builds use the frozen snapshots under `benchmark/source`, with per-file checksums. The ancestry validator checks the base commit, original file content and correspondence of the retained ERP units.

## Inputs

The repository includes the native worker sources, original ORM and value objects, the model-derived schema, fixture generators, provisioning configuration, runtime collectors and independent database verifiers. [The source manifest](../benchmark/source-manifest.json) records 149 file checksums and the source archive provenance. Files originating from T2Ti and the open DBExpress driver retain their copyright and licence notices.

[Experiment configurations](../experiments) contain the 58 accepted configurations from eight measured series. The workflow rejects configurations absent from this set. Accepted measurements and new observations have separate storage paths.

Fresh execution requires a licensed Windows Delphi installation, compiled artifacts, pinned dependencies and the reviewer's GCP account. Neither private credentials nor licensed SDK binaries are distributed.

## Analysis reproduction

Analysis uses the tracked accepted inputs and requires no cloud account, private checkout or runtime binaries.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/analyze.py
python3 scripts/validate_repository.py
python3 reviewer/validate.py
python3 scripts/validate_upstream.py
python3 -m unittest discover -s reviewer -p 'test_*.py'
```

The accepted data contain point values, raw-source checksums, exclusions, selected pricing inputs and the teardown observation. The analysis reproduces tables and figures from these accepted inputs. Reinspection of historical native traces requires the retained raw files; those files are not included in the tracked analysis dataset.

Offline infrastructure and runtime checks:

```sh
terraform -chdir=infrastructure/storage init -backend=false
terraform -chdir=infrastructure/storage validate
terraform -chdir=infrastructure/workload init -backend=false
terraform -chdir=infrastructure/workload validate
```

```powershell
.\reviewer\check_runtime.ps1
```

These checks parse and validate scripts without creating resources. Terraform initialization downloads the locked provider.

## Native build

Use an official, licensed Delphi Windows installation with the Win32 SDK. The measured workers use Delphi DBExpress, the source-built open ODBC driver, the official SDK adapter and MySQL Connector/ODBC. There is no DataSnap application-server build.

On Windows, invoke the build script with the installation's `rsvars.bat` path:

```powershell
.\reviewer\build.ps1 -RsVars 'C:\Program Files (x86)\Embarcadero\Studio\37.0\bin\rsvars.bat'
```

The installation path is an example; use the path of the licensed installation. The script builds the frozen driver and worker sources into `reviewer/inputs/native`, records compiler and artifact checksums, and retains build logs. The build receipt states that compilation alone does not establish runtime correctness. The historical qualification receipt supplied to the native workers identifies their original qualification lineage. New measurements additionally require independent verification of the new execution.

Place the six dependencies listed in [the dependency manifest](../benchmark/dependencies.json) in `reviewer/inputs/dependencies` under their manifest names. File hashes are authoritative. Public acquisition URLs are provided. Microsoft redistributable aliases can change; a changed download is rejected rather than admitted as the measured dependency. Redistributables must also pass Windows signature verification.

## Provisioning and measurement

Copy [the configuration example](../reviewer/config.example.json) to the ignored `reviewer/config.json`. Supply the GCP project, unique bucket name, resource prefix, image, region and input paths. Authenticate the GCP CLI and Terraform provider using the reviewer's account. Enable Compute Engine and Cloud Storage APIs in that project. Quota, permissions and Windows licensing are account prerequisites.

An image family is resolved to a concrete image during Terraform planning and recorded in the outputs. Supply that concrete image path when reproducing an execution. The default topology uses Windows Server 2025, private same-zone networking, e2-standard-2 hosts, 80-GiB disks and a 2-GiB InnoDB buffer pool. Application disk type follows the selected recorded series. The storage stack creates a private bucket and runtime service account. The workload stack creates an independent network, NAT and compute instances. The runtime account can read objects and create new observations; it cannot overwrite them. There are no public VM addresses. IAP access is available for Windows administration. Storage and workload states are local to each run, with independent provider working directories.

For example, configure the recorded two-target read point:

```sh
python3 reviewer/workflow.py configure --series read-targets --point 2 --operation READ
```

The command prints the run directory. Use that exact directory in subsequent commands:

```sh
python3 reviewer/workflow.py plan --run reviewer/runs/RUN_ID
python3 reviewer/workflow.py apply --run reviewer/runs/RUN_ID
python3 reviewer/workflow.py plan --run reviewer/runs/RUN_ID
python3 reviewer/workflow.py apply --run reviewer/runs/RUN_ID
python3 reviewer/workflow.py prepare --run reviewer/runs/RUN_ID
python3 reviewer/workflow.py measure --run reviewer/runs/RUN_ID
python3 reviewer/workflow.py collect --run reviewer/runs/RUN_ID
python3 reviewer/workflow.py verify --run reviewer/runs/RUN_ID
python3 reviewer/workflow.py destroy --run reviewer/runs/RUN_ID
```

The first plan/apply pair provisions storage; the second provisions the workload. Each apply requires its saved plan.

`RUN_ID` is a placeholder for the identifier printed by configuration. `plan` and `apply` perform cloud operations. `configure`, source validation and historical analysis operate locally. Each run uses one selected configuration. Independent runs must use distinct resource prefixes and bucket names, or the preceding state must be explicitly reconciled before reuse.

Preparation generates the frozen 40-table fixture and imports it into the primary database or independent shards. Cluster secondaries receive the primary dataset through native MySQL clone recovery. The cluster remains three members for the read and multi-primary comparisons. MySQL Router runs on application hosts and explicitly selects eligible destinations. Shards use disjoint customer ID ranges and direct connections to their assigned database.

Windows SYSTEM tasks retrieve hash-bound jobs from the private bucket. Application hosts run the native workload and resource sampler. Database hosts capture complete baseline and final state, native counters and decoded ROW/FULL transaction events. Baseline concurrency workers retain independent phase transitions. Application-scaling, cluster and shard series use host launch and measurement barriers. Every native worker retains the measured 60-second warmup, 180-second measurement and 30-second cooldown phases.

Verification checks native artifact and instance identities, complete worker execution, common measurement intervals, full fixture content and foreign keys, committed aggregate values, original value-object reads, connection placement and replica or shard state. Contention verification checks exact committed increments and final replica values. Failed verification does not produce an admitted throughput result. New observations and summaries remain in the run directory; the accepted historical dataset is not overwritten.

## Validation boundary

The [offline validation receipt](../evidence/reproducibility.json) records the checks and execution boundary. The distributed scripts have been checked locally for input integrity, recorded-configuration coverage, Terraform validity, PowerShell syntax and verifier behavior against retained observations. Fresh licensed Windows compilation and cloud execution of the refactored package remain unverified. Local validation does not establish that those execution steps will succeed.

The historical infrastructure receipt records resource state at its stated timestamp. Workload destruction uses its complete Terraform state and retains the separate storage stack. Evidence buckets incur storage charges. Credentials, licensed inputs, run state and generated captures are ignored by Git. Superseded files are preserved in a checksum-indexed ignored archive. Local archives are not inputs to distributed analysis or provisioning. Publication requires explicit approval.
