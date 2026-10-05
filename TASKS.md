# Repository verification record

| Component | Recorded state | Evidence |
|---|---|---|
| Native sales CRUD | Independently qualified within the worker scope | [Methods](docs/experimental-methods.md) |
| Measured configurations | 58 accepted points from eight series | [Results](docs/results.md) and [configuration inputs](experiments) |
| Cost analysis | Topology estimates derived from recorded pricing | [Cost analysis](docs/cost-analysis.md) |
| Historical infrastructure teardown | Compute, disks and NAT removed at the recorded observation | [Infrastructure receipt](evidence/accepted/infrastructure.json) |
| ERP ancestry | Original base commit and application tree retained | [Source validation](scripts/validate_upstream.py) |
| Distributed native and fixture inputs | Frozen source files and checksums included | [Source manifest](benchmark/source-manifest.json) |
| Reviewer provisioning and measurement interface | Implemented; local validation only | [Reproducibility](docs/reproducibility.md) |
| Refactored package execution | Fresh Windows compilation and cloud replay unverified | [Execution status](docs/reproducibility.md#validation-boundary) |
| Publication | Requires explicit approval | [Operating instructions](PROMPT.md) |

Worker qualification covers the native sales path. Full GUI ERP qualification is outside the measured scope.
