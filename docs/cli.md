# CLI reference

[Documentation index](README.md)

The command structure is:

```text
dockflow pipelines [--config PATH] [--endpoint URL | --local] [--json] COMMAND ...
```

Group options precede the command. `dockflow --help`, `dockflow --version` and
nested `--help` commands are offline and do not start infrastructure. An endpoint
selects a persistent service; otherwise commands use the selected local project.
See [configuration](configuration.md) for discovery and endpoint precedence.

## Execute a pipeline

```bash
dockflow pipelines --config PROJECT_CONFIG run training
dockflow pipelines --endpoint http://127.0.0.1:8080 run training --no-wait
dockflow pipelines --config PROJECT_CONFIG run ./training.yaml --parameter seed=42
```

Replace uppercase operands throughout this page with actual paths or IDs.
The `run` operand is a registered name, immutable `definition_…` ID, or compiled
YAML/JSON file. A remote file operand is read on the client and sent as content.

| Option | Purpose |
| --- | --- |
| `--name TEXT` | Human-readable Run name. |
| `--experiment EXPERIMENT_ID` | Experiment ID; absent means `Default`. |
| `--parameter NAME=JSON` | Repeat for typed parameter assignments. |
| `--input NAME=ARTIFACT_ID` | Repeat for declared root artifact inputs. |
| `--from TASK` | Select this exact qualified task and its descendants. |
| `--tasks TASK[,TASK…]` | Select only these exact tasks; mutually exclusive with `--from`. |
| `--bind TASK.INPUT=ARTIFACT_ID` | Bind a historical artifact to a selected task input. |
| `--use-execution TASK=ATTEMPT_ID` | Select a compatible successful historical producer's complete output set. |
| `--scope global\|keyed\|run\|none` | Reuse namespace or fresh execution. |
| `--scope-key KEY` | Required for keyed scope; rejected for other explicit scopes. |
| `--wait` / `--no-wait` | Service mode waits by default. Direct mode always waits. |
| `--idempotency-key KEY` | Service-only key for replaying an uncertain submission. |
| `--output none\|trimmed\|full` | Human result details; defaults to `trimmed`. Does not hide ordinary component messages. |
| `--output-limit INTEGER` | Characters per verbose display block in trimmed mode; default 2000, minimum 128. |
| `--dockflow-output` / `--no-dockflow-output` | Show/hide normal Dockflow progress and human results; shown by default. |
| `--component-output` / `--no-component-output` | Show/hide local component stdout/stderr; shown by default. Full logs are always saved. |

Parameters are JSON, not arbitrary strings. For a string use shell quoting that
preserves its JSON quotes, for example `--parameter 'label="baseline"'`. Numbers
such as `count=10`, booleans such as `enabled=true`, and JSON arrays/objects retain
their declared types. Duplicate, unknown or mismatched assignments fail.

Partial execution never silently executes omitted prerequisites. Supply valid
historical bindings or include the prerequisites. See [reuse](artifacts.md).

Every fresh accepted submission creates a Run, even if its tasks reuse history.
The service CLI generates an idempotency key if none is supplied; errors with
uncertain acceptance report the key. Retry with that same key and request to
avoid creating another Run. A changed request with the same key conflicts.

## Control run output

```bash
dockflow pipelines run training                       # Trimmed details
dockflow pipelines run training --output none         # Logs and Run ID/status
dockflow pipelines run training --output full         # Complete run record/details
dockflow pipelines run training --output-limit 500    # Shorter previews
dockflow pipelines run training --no-dockflow-output  # Component output only
dockflow pipelines run training --no-component-output # Dockflow progress/results only
dockflow pipelines run training --no-dockflow-output --no-component-output
# No normal output on success; Dockflow warnings/errors remain visible
```

These examples omit any required pipeline parameters; keep the same parameters
and bindings you normally pass. `trimmed` shows the Run ID/state, output artifact
IDs and scalar results, with long blocks visibly shortened. `none` suppresses
result details while keeping identity, status, submission key and errors.
`full` prints the complete accepted Run, including its compiled definition and
resolved plan. Artifact descriptors contain paths and metadata, not payload bytes.

For direct local execution, the same option hides/trims KFP's verbose task-output
summaries and recognized executor-input JSON. It never hides ordinary component
messages, changes artifacts, or truncates retained logs. The default preview
limit applies separately to each verbose block. Group `--json` always returns the
complete machine-readable result on stdout regardless of the human display mode;
local diagnostics and component stdout/stderr go to terminal stderr.

The two visibility switches work independently of `--output`. Hiding component
output removes container stdout/stderr, the log heading and stream labels without
disabling capture. Hiding Dockflow output removes progress, task separators, the
human result and recognized KFP executor bookkeeping inside the containers:
component lookup/loading, input JSON and output-file INFO messages. This also
applies with `--output full`; your own component traces and stream labels remain.
Unknown messages, malformed metadata and container warnings/errors stay visible
when component output is enabled. Ordinary Python logging is preserved even
when it inherits KFP's log formatter. Dockflow
warnings, failed/cancelled/interrupted Run diagnostics and exit codes remain
available. Suppressed component logs are not automatically replayed on failure.
Explicit `--json` still emits the complete result even with both switches off.

Use `runs show RUN_ID` for the full record and `logs RUN_ID` for complete retained
logs later. Remote `run` uses the same final-result display modes; retrieve remote
component logs with the separate `logs` command. Remote `run` accepts the
component-output switch but does not start fetching logs; explicit log inspection
is unaffected by either switch.

## Inspect and manage

| Command after `dockflow pipelines` | Behavior |
| --- | --- |
| `definitions list [--name NAME]` | Registered definitions and retained versions. |
| `definitions show NAME_OR_DEFINITION_ID` | Exact snapshot, digest and diagnostics. |
| `definitions validate NAME_OR_PATH` | Validate without running. |
| `definitions refresh` | Reconcile configuration-owned mappings; preserve uploads/history. |
| `components list [--name NAME]` | Embedded and explicitly registered component contracts. |
| `components show COMPONENT_OR_DEFINITION_ID` | Component types, compiled content and executor. |
| `runs list [--state STATE] [--experiment ID]` | Run history. |
| `runs show RUN_ID` | Parameters, selection, plan, task IDs, outputs and errors. |
| `runs cancel RUN_ID` | Request cancellation; safe to repeat. |
| `tasks show TASK_ID` | Attempts, bindings, state and reuse decisions. |
| `artifacts list [--type TITLE] [--availability STATUS]` | Artifact catalog. |
| `artifacts show ARTIFACT_ID` | Fingerprint, URI, type, provenance, availability and pin. |
| `artifacts register --uri URI --type TITLE` | Keep an external reference. |
| `artifacts import --uri URI --type TITLE` | Create a managed immutable copy. |
| `artifacts upload PATH [--archive-mode keep\|extract] [--type TITLE]` | Upload client-local bytes and register a manual managed file/directory artifact. |
| `artifacts pin ID` / `artifacts unpin ID` | Set/remove an explicit retention pin. |
| `experiments create NAME [--description TEXT]` | Create a project-unique grouping. |
| `experiments list [--name NAME]` / `experiments show ID` | Inspect groupings. |
| `capabilities` | Installed/server versions, supported profile and limits. |

List commands return one page, with `--page-size` from 1–200 (default 50) and
`--page-token` for continuation. They do not fetch unlimited history automatically.
Use only filters meaningful for that collection; unrelated filters are rejected.

Artifact creation also accepts `--type-version`, `--version` and repeated
`--metadata NAME=JSON`. Built-in types default to schema version `0.0.1`; custom
types need an explicit schema version. Data revision labels and type schema
versions are different concepts.

## Logs

```bash
dockflow pipelines --endpoint http://127.0.0.1:8080 logs RUN_ID --follow
dockflow pipelines --config PROJECT_CONFIG logs RUN_ID --task TASK_ID
dockflow pipelines --config PROJECT_CONFIG --json logs RUN_ID --limit-bytes 65536
```

Use `--attempt ATTEMPT_ID` to inspect a specific retry. Task/attempt filters must
belong to the Run. JSON logs return one bounded page with `entries`, `next_cursor`
and `terminal`; continue using `--cursor`. The byte limit defaults to and cannot
exceed 65536. `--json --follow` is rejected because follow is a stream, not one
JSON document.
Foreground local `run` displays component log lines live as they are persisted.
For service Runs, `logs RUN_ID --follow` polls newly retained output while the
container is running. Components must flush their output (for Python, use
`print(..., flush=True)` or `python -u`); Dockflow cannot flush their buffers.
A final partial line appears at task completion. Reused tasks have no new
container output; inspect their original producer's logs when needed.

Component ANSI colors are preserved in a terminal. Redirected foreground output
is plain text; use `NO_COLOR=1 dockflow pipelines ... run ...` to disable colors
in its terminal presentation. Saved logs always retain the original text.

## Service and maintenance

```bash
dockflow pipelines --config PROJECT_CONFIG serve --host 127.0.0.1 --port 8080
dockflow pipelines --config PROJECT_CONFIG metadata check --verify-contents
dockflow pipelines --config PROJECT_CONFIG metadata rebuild
dockflow pipelines --config PROJECT_CONFIG clean
```

`metadata rebuild` and `clean` preview by default. `--apply` is explicit intent to
perform the validated plan. Rebuild application requires offline direct ownership;
the live API only returns its plan. Cleanup needs an idle owner and preserves
committed artifacts and history. Follow [operations](operations.md) and
[recovery](persistence.md), especially after interrupted execution.

## Output and exit status

Human output contains resource details and IDs. Group `--json` emits one document
on stdout: `{"schema_version": 1, "result": …}`. A failed JSON command emits
`{"schema_version": 1, "error": …}` on stderr with empty success stdout. Component
logs from local execution go to stderr and do not contaminate JSON results.
Retained logs can also be retrieved separately.

| Exit | Meaning |
| --- | --- |
| `0` | Success; for waited execution the Run succeeded. `--no-wait` means accepted, not completed. |
| `1` | Operational failure, failed/cancelled/interrupted Run, or detached wait. |
| `2` | Invalid CLI usage, such as an unknown command or missing required operand. |

Ctrl+C during direct execution requests interruption and container termination.
Ctrl+C in a remote waiting client detaches the client and leaves the Run owned by
the service. Use `runs cancel` to request actual service-side cancellation.

## Resource deletion and storage cleanup

See [Deletion and storage cleanup](cleanup.md) for dependency-protected Run,
execution and artifact deletion, file inventories, explicit manual-artifact
protection, DANGER confirmation and optional deployment retention. Legacy `clean`
continues to remove only disposable workspaces.
