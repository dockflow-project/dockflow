# Troubleshooting

[Documentation index](README.md)

Start with `dockflow pipelines capabilities`, the selected configuration and the
exact failure message. In service mode also inspect `/health/ready` and service
logs. Preserve Run/Task/Attempt IDs and API `request_id` values when investigating.

| Symptom | Check / action |
| --- | --- |
| `uv: command not found` | Install uv using the link in [installation](installation.md), then reopen the shell if needed. |
| `dockflow: command not found` | Activate the environment, or use `uv run --all-packages --all-extras dockflow` from the checkout. |
| Missing KFP, Docker, MLMD or service dependency | Install the relevant [extras](installation.md#select-only-the-needed-capabilities); remote-only commands do not need execution extras. |
| Selected configuration does not exist | Fix `--config`/`DOCKFLOW_PIPELINES_CONFIG`; an invalid explicit selection never falls back. `serve` requires explicit selection. |
| Unknown configuration fields | Use schema version 1 and the exact [configuration fields](configuration.md); arbitrary nested environment variables are not supported. |
| Cannot reach selected service | Verify host/port, readiness and token/TLS settings. A failed remote connection never switches to local execution. |
| Owner conflict | Use the running service's explicit endpoint, or wait/stop that owner normally. Inspect reported UUID/hostname/PID/mode. Never remove its lock file. |
| Prior execution requires reconciliation | Start the service with the same config/daemon and resolve retained work before another direct Run. See [recovery](persistence.md). |
| MLMD import fails despite installed package | Check Python, OS/architecture and libc compatibility. Use the qualified Linux reference environment; installation metadata is not full runtime qualification. |
| Docker connection fails while `docker ps` works | Dockflow uses SDK environment settings, not implicit CLI context selection. Check `DOCKER_HOST` and Docker TLS variables for the Python process. |
| Component image missing | Build/load into the owner's engine or provide a reachable registry. Host and inner Compose caches are separate. Check `images.pull_policy`. |
| Container cannot see a staged input | Make the execution directory visible at the same absolute path to the owner and daemon; check permissions and the selected engine. |
| External source URI rejected | Use an absolute `file://` or admitted `s3://` URI and configure allowed roots/prefixes. A client-local file path is not uploaded to a remote service. |
| Artifact source changed / fingerprint mismatch | Preserve the original if needed and register the new contents as a new artifact; do not rewrite the old descriptor. |
| Unsupported capability | Inspect definition/task diagnostics and [compatibility](compatibility.md). Remove or redesign unsupported compiled constructs before running. |
| A successful process still produces a failed task | Check required outputs, parameter types, executor metadata, input mutation and publication errors. Exit zero alone does not commit outputs. |
| Expected reuse did not happen | Inspect task reuse reasons, compiled caching flags, image identity, actual inputs and artifact availability. `--scope none` deliberately disables reuse. |
| Partial selection cannot resolve prerequisites | Bind compatible historical inputs or include omitted tasks. Explicit ordering dependencies still need compatible successful history. |
| Pipeline/version upload conflicts | Use a unique pipeline/version name. Uploads are immutable and cannot overwrite a configuration-owned registration. |
| HTTP 429 | The service waiting queue is full; inspect queued Runs or deliberately change `service.queue_capacity`. |
| Metadata rebuild fails through API | Applying rebuild is offline/direct-only. Stop service, resolve uncertain execution, preview then apply locally. |
| Browser reports unauthorized | Supply the service token for the current page session, or correct reverse-proxy authentication. Health/static pages being reachable does not mean API access is authorized. |

## Diagnose one failed task

```bash
dockflow pipelines --endpoint http://127.0.0.1:8080 runs show RUN_ID
dockflow pipelines --endpoint http://127.0.0.1:8080 tasks show TASK_ID
dockflow pipelines --endpoint http://127.0.0.1:8080 logs RUN_ID --task TASK_ID
```

Use the task's attempt IDs to distinguish retries from one computation. The
browser provides the same navigation and bounded log pages. Keep failed work
until diagnosis is complete; `clean --apply` may remove eligible scratch paths.

## Distinguish state from payloads

If the history says a Run succeeded but an artifact is missing, run
`metadata check --verify-contents`. History records what happened; current
availability records whether the bytes can still be read. Restore lost bytes
from a verified backup or rerun the intended computation. Rebuilding an index
does not regenerate artifact contents.

If an unexpected error remains, capture the command or HTTP request shape,
redacted effective configuration, versions, relevant IDs and logs. Exclude
credentials and private input/output data. See [contributing](../CONTRIBUTING.md)
for reporting and reproducing an issue.
