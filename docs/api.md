# HTTP API guide

[Documentation index](README.md) · [Generated route/model reference](reference/api.md)

The native API base path is `/dockflow/v1`. Run the service explicitly with a
project configuration, then use:

- `/ui/` for the [browser interface](ui.md).
- `/dockflow/v1/docs` for the packaged API explorer, without external CDN assets.
- `/dockflow/v1/openapi.json` for the live OpenAPI 3.1 document.
- `/health/live` and `/health/ready` for process and admission health.

A [checked-in OpenAPI snapshot](reference/openapi.json) and generated reference
are available for offline reading. They are generated from the same application
contract, without starting the service. Regenerate after an API change with
`python tools/generate_api_docs.py`; use `--check` to detect drift.

## Requests and authentication

Requests and responses use UTF-8 JSON. Native request bodies are objects;
duplicate keys, unknown fields, non-finite values and integers outside
±(2^53−1) are rejected. Empty-body actions such as cancellation accept `{}`.
The default request limit is 16 MiB, configurable by the execution owner.
The two KFP definition upload routes use multipart form data instead.

By default the service is for a trusted loopback/private environment. When
`service.token_file` is configured, send:

```http
Authorization: Bearer YOUR_TOKEN
```

Use a secret file and TLS termination for a nonlocal deployment. The CLI reads
`client.token_file`; the browser keeps a supplied token in memory for its current
page session. Public static pages and health probes do not grant access to the
protected resource APIs. See [configuration](configuration.md) and
[security](../SECURITY.md). Do not place credentials in URLs or pipeline parameters.

The service rejects missing, duplicate or malformed `Host` headers with HTTP 400.
Authentication uses the routed request path, including configured proxy prefixes.
The remote CLI rejects HTTP redirects, including redirects to the same host;
configure the final service URL and base path directly. This prevents tokens and
request bodies from being forwarded to another endpoint.

## List and inspect

```bash
curl --fail http://127.0.0.1:8080/dockflow/v1/capabilities
curl --fail 'http://127.0.0.1:8080/dockflow/v1/runs?page_size=20&state=succeeded'
curl --fail http://127.0.0.1:8080/dockflow/v1/runs/RUN_ID
```

Resource collections include pipelines, definitions, components, experiments,
runs, tasks, attempts and artifacts. Resource detail routes take their returned
opaque IDs. A pipeline is the catalog identity; its immutable versions are
definitions. Artifact lineage links producers and consumers through task IDs.

Collection responses have this shape:

```json
{"items": [], "next_page_token": null}
```

`page_size` defaults to 50 and accepts 1–200. Pass `next_page_token` back as
`page_token` with the same filters to continue. Tokens are opaque and bound to
the query; do not decode or manufacture them. The API returns one page at a
time. Consult the generated reference/live explorer for supported filters.

## Submit and monitor a Run

First obtain a definition ID from the definition catalog. Then submit:

```bash
curl --fail-with-body -X POST http://127.0.0.1:8080/dockflow/v1/runs \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: tutorial-request-001' \
  --data '{"definition_id":"DEFINITION_ID","display_name":"Tutorial","parameters":{"count":10},"reuse":{"scope":"global"}}'
```

Replace `DEFINITION_ID` with an actual `definition_…` value. New acceptance
returns HTTP **202**, the Run resource, and a `Location` header. This means queued
durably, not completed. Poll `GET /dockflow/v1/runs/RUN_ID` until a terminal state:
`succeeded`, `failed`, `cancelled` or `interrupted`.

An identical request with the same `Idempotency-Key` returns the original Run
with HTTP **200**. Reusing that key for different content returns a conflict.
Keep the same key when a connection fails after a possibly accepted submission;
a fresh key may create another Run. The native CLI manages a key for service
submissions automatically. Idempotency and task reuse solve different problems.

A request may instead contain `pipeline_spec` with a compiled document object
and optional matching `source_text`. Supply exactly one of `definition_id` or
`pipeline_spec`. The full `RunCreate` schema also supports `experiment_id`, typed
`inputs`, `selection`, `bindings`, `use_executions` and `reuse`. No server-side
Python compilation or arbitrary URL fetch happens during submission.

Cancel accepted work explicitly:

```bash
curl --fail-with-body -X POST http://127.0.0.1:8080/dockflow/v1/runs/RUN_ID/cancel \
  -H 'Content-Type: application/json' --data '{}'
```

Cancellation is repeatable. A completed result remains historical; cancellation
does not erase committed outputs. Disconnecting from a client does not cancel
the Run.

## Read logs

`GET /dockflow/v1/runs/RUN_ID/logs` accepts optional `task_id`, `attempt_id`,
`cursor` and `limit_bytes` (default/maximum 65536). Filters must refer to that Run.
Responses contain `entries`, `next_cursor` and `terminal`. Each entry retains
sequence, timestamp, task/attempt identity, `stdout`/`stderr`/`system` stream and
text. Poll the next cursor until the Run is terminal and the page is drained.
This endpoint transports logs, not artifact payload bytes.
Task output is persisted while the container runs, so polling retrieves new
logs before completion. Component-side buffering can delay output until flushed.
Raw text retains ANSI color sequences if emitted; display clients can strip them.

## Resource reference names

The browser uses `POST /dockflow/v1/ui/reference-names` to resolve up to 200
referenced IDs per read-only request, without scanning catalog pages. Each item
in `references` supplies `collection` and `id`. Supported collections are runs,
tasks, attempts, pipelines, definitions, components and experiments. The response
returns deduplicated `items` with the collection, ID, human context `name` and
`available` flag. Missing/retired targets or context return null/unavailable.
Execution/Task names describe their components; Run names describe their compiled
pipelines. Authentication, same-origin admission and normal request limits apply;
the lookup is available during execution and changes no records. See the
[generated schema](reference/openapi.json) for exact models.

## Filter autocomplete

`GET /dockflow/v1/ui/filter-options?collection=runs&search=training` returns up to
ten recent matches across names and IDs. Omit `search` for the latest records.
Use `collection=attempts` for executions. Workloads sort by execution start with
creation fallback; other resources use creation/definition registration dates.
Each item contains `id`, human-readable `name`, exact filter `value` and
`recent_at`; the response also has the exact `remaining_count` beyond the ten
returned options. `collection=artifacts&field=type` suggests distinct artifact types.
For dependent options, pass `definition_id` with components, `experiment_id`
with definitions, `experiment_id`/`definition_id` with runs, `run_id` with tasks,
or `run_id`/`task_id` with attempts. Definitions scoped to an experiment are only
versions used by its live Runs. Counts respect these scopes and distinct types.

Native collection lists accept `search` for the same literal ID/name substring
matching, combined with existing exact filters and cursor pagination. `%` and
`_` are literal characters. Search is limited to 256 characters; database LOWER
semantics provide case-insensitive ASCII matching on SQLite. Suggestion requests
require the same project authentication as other data reads and do not access
artifact files. See the [generated schema](reference/openapi.json).

## Upload and register client files

`POST /dockflow/v1/artifacts/upload` accepts multipart form data with one
`uploadfile` file and one `options` JSON text field. On success it returns 201 and
the committed manual managed artifact descriptor. For example:

```bash
curl --fail-with-body SERVICE_URL/dockflow/v1/artifacts/upload \
  -F 'uploadfile=@./dataset.zip' \
  -F 'options={"type":{"schema_title":"system.Dataset","schema_version":"0.0.1"},"archive_mode":"extract","version":"dataset-v1"}'
```

Use the deployment's bearer authentication when enabled. `archive_mode` defaults
to `keep`; `extract` requires a valid `.zip` and creates a directory artifact.
Optional `metadata` is a JSON object. The service chooses the destination and
rejects query arguments, unknown fields or extra/duplicate multipart parts.

The standard-library Python client sends local file bytes using the same API:

```python
from pathlib import Path
from dockflow_pipelines.client import Client

artifact = Client("https://service.example").upload_artifact(
    Path("dataset.zip"),
    type={"schema_title": "system.Dataset", "schema_version": "0.0.1"},
    archive_mode="extract",
    metadata={"description": "Manually supplied dataset"},
)
```

Configure client TLS/token options as for other native requests. There are no
automatic upload retries; after an uncertain response, inspect the artifact list
before submitting again. [Upload usage](artifacts.md#upload-and-register-a-new-artifact)
explains request/ZIP limits and manual retention. This native endpoint is separate
from KFP compiled-pipeline uploads.

## Register data and group Runs

Create a managed copy from a server-visible allowed source:

```json
{
  "operation": "import",
  "uri": "file:///inputs/dataset.csv",
  "type": {"schema_title": "system.Dataset", "schema_version": "0.0.1"},
  "version": "dataset-v1",
  "metadata": {"description": "Training input"}
}
```

Send that object to `POST /dockflow/v1/artifacts`; use `operation: "register"`
for a reference. This is not a client file upload. `GET /artifacts/ID` returns
metadata/location; it does not provide a general binary download route.
`GET /artifacts/{artifact_id}/contents` provides bounded CSV/JSON/raster-image/text
previews and directory inventory using optional `path`, `format`, `page_size` and
opaque `page_token`. It accepts artifact-relative paths rather than arbitrary URIs.
CSV/directory responses expose continuation tokens; changed/expired cursors require
restarting from the beginning. See [Contents usage](ui.md#artifacts-and-lineage)
and the generated schema for response fields and limits.

`POST /dockflow/v1/experiments` accepts `display_name` and optional `description`.
Use the resulting experiment ID in a Run request. Names are unique within the
project; the API does not accept a display name where an experiment ID is required.

Maintenance endpoints expose definition refresh/validation, metadata checks,
rebuild planning and cleanup planning/application. They enforce idle ownership
where required. Applying a metadata rebuild is offline-only and rejected by a
running service. See [operations](operations.md).

## KFP client-compatible adapter

The `/apis/v2beta1` adapter targets the documented KFP 2.17 client subset. It uses
KFP response models and `google.rpc.Status`-shaped errors, rather than native
Dockflow resource/error envelopes.

| Official client operation | Supported behavior |
| --- | --- |
| `create_experiment`, `list_experiments`, `get_experiment` | Project-local groupings. |
| `upload_pipeline` | Register one compiled UTF-8 YAML/JSON definition and initial version. |
| `upload_pipeline_version` | Add an immutable named version to an API-owned pipeline. |
| `list_pipelines`, `get_pipeline` | Inspect catalog entries. |
| `list_pipeline_versions`, `get_pipeline_version` | Inspect retained versions. |
| `run_pipeline`, `get_run`, `list_runs` | Submit/inspect supported compiled invocations. |
| `terminate_run` | Request cancellation. |

Example with a KFP client environment and an already prepared component image:

```python
import kfp

client = kfp.Client(host="http://127.0.0.1:8080")
pipeline = client.upload_pipeline("training.yaml", pipeline_name="training")
version = client.upload_pipeline_version(
    "training-v2.yaml",
    pipeline_id=pipeline.pipeline_id,
    pipeline_version_name="training-v2",
)
experiment = client.create_experiment("Evaluation")
run = client.run_pipeline(
    experiment_id=experiment.experiment_id,
    job_name="Training v2",
    pipeline_id=pipeline.pipeline_id,
    version_id=version.pipeline_version_id,
    params={"seed": 42},
)
print(run.run_id)
```

The files and `seed` parameter stand for your own pipeline's declared interface.
The service owns storage/execution; `pipeline_root` overrides do not relocate its
artifact store. Uploaded contracts include component commands/images, so there
is no separate component-code registration requirement.

The upload routes are `POST /apis/v2beta1/pipelines/upload` and
`POST /apis/v2beta1/pipelines/upload_version`. They accept exactly one
`uploadfile` multipart part. Query `name`/`display_name` specifies the catalog or
version name; version upload requires `pipelineid`. Names must be unique in their
scope. Raw compiled YAML/JSON is supported; archives, remote URLs, image layers,
artifact payloads and nonempty Kubernetes namespaces are rejected.

Do not infer whole-server compatibility from these methods. Recurring schedules,
archive/delete operations and unsupported filters/fields fail explicitly.
[Compatibility](compatibility.md) separates implemented features from future work.

The KFP 2.17 wait helper does not recognize `CANCELED` as a terminal state.
Use `get_run` or the native CLI to verify cancellation; Dockflow preserves the
truthful wire state instead of changing it to satisfy that client helper.

## Errors

Native errors have one stable envelope:

```json
{
  "error": {
    "code": "INVALID_ARGUMENT",
    "message": "A concise explanation",
    "details": [{"field": "parameters.count", "reason": "Invalid value"}],
    "request_id": "REQUEST_UUID"
  }
}
```

Details can be empty. Ownership failures add sanitized owner/state diagnostics;
never use the lock metadata as permission to take over. Retain `request_id` when
investigating a server error.

| HTTP status | Typical meaning |
| --- | --- |
| `400` | Invalid request, field, query or parameter. |
| `401` / `403` | Authentication or authorization failure. |
| `404` | Unknown resource. |
| `409` | Conflicting owner, name, idempotency request or offline-only operation. |
| `410` | Requested retained data no longer available under the relevant contract. |
| `413` | Request too large. |
| `422` | Unsupported capability. |
| `429` | Waiting queue full. |
| `500` | Internal failure; inspect service logs using the request ID. |
| `503` | Unavailable dependency, ownership mechanism or recovery/admission state. |

Use the actual error code/message to distinguish cases sharing an HTTP status.
An HTTP success from a submission does not imply the pipeline eventually succeeds.

## Resource deletion and storage cleanup

See [Deletion and storage cleanup](cleanup.md) for dependency-protected Run,
execution and artifact deletion, file inventories, explicit manual-artifact
protection, DANGER confirmation and optional deployment retention. Legacy `clean`
continues to remove only disposable workspaces.
