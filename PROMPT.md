# Repository operating instructions

## Scope

Maintain the distributed replay scripts, research documentation, accepted measurements and local analysis described in [README.md](README.md). [Study design](docs/study-design.md) defines the experimental scope. [TASKS.md](TASKS.md) records completion status.

Use single-agent execution. Local preservation branches are not publication inputs. Publication and upstream pushes require explicit user approval. Cloud provisioning requires an explicit execution request. Reviewer provisioning uses independent run-local Terraform state. Use independent Terraform state for reproduction.

## Preservation

Move superseded documents and intermediate artifacts into the ignored `.archive/` directory. Preserve their contents and record original paths, destination paths and SHA256 checksums in the archive manifest. Preserve existing modifications and untracked files.

Keep credentials, licensed installers, raw runtime data, cloud state and the independent upstream checkout outside Git tracking. Preserve upstream application files at their original paths. Research additions use separate directories and frozen build inputs. Do not modify original upstream business source as part of documentation maintenance.

## Writing

Use precise scientific language. Separate methods, observations, interpretation and limitations. State measurable quantities, units, conditions and evidence sources. Avoid chronological execution narratives, conversational commentary, promotional language, rhetorical contrasts and em dashes.

Git records document revisions. Do not add document version headers or revision suffixes to filenames. Retain software versions, timestamps, run identifiers and checksums where they support reproducibility.

## Validation

Preserve accepted numerical results and timing boundaries. Keep excluded measurements excluded. Distinguish workloads with different read semantics or ownership rules. Do not infer missing observations or generate figures for unexecuted experiments.

Check documentation links, data consistency, archive integrity and Git exclusions after restructuring. Analysis commands must not initiate workloads or mutate cloud resources.
