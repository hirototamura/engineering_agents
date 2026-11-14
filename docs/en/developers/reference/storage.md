# Internal storage contracts

Artifact meanings and scenario-specific outputs are defined in the [user artifact reference](../../users/reference/artifacts.md). This page specifies persistence helpers, recovery behavior, and limits relevant to a code change.

## Paths and recreation

`scenario/jobs/resolve.py` resolves explicit output directories or a results root plus run ID, and validates IDs before creating a derived path. Public root precedence, default tracks, and ID syntax are defined in the [output configuration contract](../../users/reference/configuration.md#output-directories). A resolver change must preserve that contract and path-traversal rejection.

`EventLog.prepare_run_dir()` recreates existing generic run directories. `remove_run_directory()` refuses files and nonempty directories without recognized run markers unless forced. This protects against deleting an arbitrary directory; it does not preserve an existing run when recreation is requested. Cube instead refuses a nonempty output directory and keeps design runs immutable.

## Writes and reads

`EventLog.append()` accepts only its named streams: messages, telemetry, health metrics, EPS telemetry, events, design state, and memory reasoning. Each append opens the corresponding JSONL file in append mode. `write_summary()` replaces `summary.json`. These operations are not a multi-file transaction or an immutable artifact service.

`ArtifactStore.read_json()` returns `{}` for a missing file, malformed JSON, or a non-object value. It does not catch every I/O error. `write_json()` creates parent directories and replaces the named JSON document. This lenient reader is appropriate only when absence is allowed; the executor independently uses strict summary validation.

`SessionStore` writes per-agent JSONL with a lock within that store instance. Loading skips malformed lines. It is not a cross-process locking or access-control service. `ClaimsRegistry` persists standing/retracted claims and performs a phrase-based sweep; loading damaged input clears its in-memory claim list.

## Persistence is not one uniform service

| Object | Write behavior | Read/failure behavior | Caller obligation |
| --- | --- | --- | --- |
| `EventLog` | Append one JSONL row; replace summary | Unknown stream rejected | Choose the scenario's row semantics and output lifecycle |
| `ArtifactStore` | Named JSON replacement | Missing/malformed/non-object JSON becomes `{}` | Use only where absent data is allowed |
| `SessionStore` | Per-agent append with instance lock | Damaged lines skipped | Keep peer sessions isolated at the caller |
| `ClaimsRegistry` | Save standing/retracted assertions | Damaged load clears in-memory claims | Do not treat a phrase sweep as semantic proof |
| Executor summary reader | Does not repair failed evidence | Missing/damaged/empty/non-object summary fails | Preserve failure rather than publish fabricated completion |

The following illustrates the claims contract, not a new global document validator:

```python
claims.register(agent_id="designer", candidate_id="run-a:candidate-1", fields={"sizing": 12.0})
claims.register(agent_id="designer", candidate_id="run-a:candidate-2", fields={"sizing": 15.0})
claims.retract_except("run-a:candidate-2")
hits = claims.sweep_text("Adopt run-a:candidate-1.")
```

The old candidate's namespaced identifier is detected. Local tails are deliberately excluded because they can match multiple run IDs; phrases still shared by a standing claim are allowed. A nearby retraction marker can qualify a mention. Persisted evidence and selected-candidate IDs remain the primary basis for correctness.

## Stronger scenario guarantees

Mechanical `atomic_json()` writes finite JSON through a temporary file and replacement. Cube freezes inputs, retains incomplete evaluations separately, and uses a durable integration outbox; these guarantees do not automatically apply to other artifacts. Design code must preserve source references and avoid interpreting an absent value as a passing measurement.

Regression checks live in `tests/core/test_design_storage.py`, `tests/scenario/test_run_spec.py`, `test_write_effective_configs.py`, and cube immutability/synchronization tests. When changing storage, also inspect its readers in dashboards and analysis tools for tolerant versus strict parsing.
