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
