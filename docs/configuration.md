# Configuration reference

[Documentation index](README.md)

Dockflow Pipelines uses one strict TOML schema for local and service execution.
The smallest usable file is:

```toml
schema_version = 1

[project]
id = "my-project"
```

This creates state at `.dockflow`, filesystem artifacts at `artifacts`, and work
under `.dockflow/work`, relative to the configuration directory. It has no named
definitions; supply a compiled file to `run` or add a definition map. Merely
loading configuration does not start infrastructure or run tasks.

## File selection and precedence

For direct commands, choose the file in this order:

1. `dockflow pipelines --config PATH …`
2. `DOCKFLOW_PIPELINES_CONFIG`
3. The nearest ancestor `.dockflow-pipelines.toml`, starting at the working directory.

An invalid explicit selection fails; it does not fall back. `serve` requires an
explicit file option or environment variable and never searches parent directories.

For configurable values the order is explicit option, documented environment
override, TOML value, default. Unknown fields and invalid values fail. TOML
strings do not expand shell variables or include other configuration files.
Changes take effect on the next command or service restart, not by hot reload.

An explicit `--endpoint`, `DOCKFLOW_PIPELINES_ENDPOINT`, or `[client].endpoint`
selects remote mode in that order. `--local` overrides environment/file endpoints
and conflicts with explicit `--endpoint`. A connection failure never switches to
direct execution automatically.

## Paths and project identity

`project.id` is required: 1–128 ASCII letters, digits, dots, underscores or hyphens,
starting with a letter or digit. Keep it stable for the lifetime of the store.
Dockflow refuses to attach an incompatible project ID to existing state.

Relative `project.root` is resolved against the configuration file's directory.
Every other relative path is resolved against that root. This remains true when
invoking the CLI from a different working directory. Container configuration
contains container-visible paths. Client paths do not become server paths.

Keep control state, managed artifacts and external input roots separate. Work
must not contain or overlap protected data in a way that allows cleanup to
remove it. The documented default `.dockflow/work` is allowed; artifacts belong
outside control state. Input symlinks are not a way around allowed-root checks.

## Fields

Only `schema_version = 1` and `project.id` are required.

| Table | Field | Default / admitted values |
| --- | --- | --- |
| `project` | `root` | Configuration directory (`"."`). |
| `definitions` | `pipelines`, `components` | Empty maps of registered names to compiled file paths. Names match `[a-z][a-z0-9_-]{0,63}`. |
| `state` | `directory` | `".dockflow"`. |
| `metadata` | `backend` | `"sqlite"`; only supported backend. |
| `metadata` | `directory` | `db/` beneath state; database is `mlmd.sqlite`. |
| `execution` | `work_directory` | `work/` beneath state. |
| `execution` | `task_parallelism` | `1`; other values rejected. |
| `execution` | `timeout_seconds` | `0` (unlimited); nonnegative integer. |
| `execution` | `shutdown_grace_seconds` | `30`; nonnegative integer. |
| `execution` | `cpu_limit` | Omitted; finite positive number of CPU cores. |
| `execution` | `memory_limit_bytes` | Omitted; positive integer bytes. |
| `images` | `pull_policy` | `"if-missing"`, `"always"`, or `"never"`. |
| `artifacts` | `backend` | `"filesystem"` or `"s3"`. |
| `artifacts` | `root` | Legacy filesystem base; managed contents go below its `managed/` child. Defaults to `"artifacts"` if neither directory option is set; forbidden for S3. |
| `artifacts` | `managed_root` | Exact filesystem managed directory; no extra child appended. Alternative to `root`; forbidden for S3. |
| `artifacts` | `external_roots` | `[]`; allowed local source directories. |
| `artifacts` | `allowed_uri_prefixes` | `[]`; allowed credential-free `s3://bucket/path/` source prefixes. |
| `artifacts` | `endpoint`, `bucket` | Required for S3; forbidden for filesystem. |
| `artifacts` | `prefix` | `""`; optional S3 key prefix, no `.`/`..` segments. |
| `artifacts` | `tls_verify` | `true`. |
| `artifacts` | `allow_insecure_http` | `false`; must explicitly be true for an HTTP S3 endpoint. |
| `reuse` | `scope` | `"global"`, `"keyed"`, `"run"`, or `"none"`. |
| `reuse` | `scope_key` | Omitted; required and nonempty for keyed scope. |
| `policies` | `file` | Omitted; optional definition-bound JSON policy. |
| `client` | `endpoint` | Omitted; absolute HTTP(S) URL without embedded credentials, query or fragment. |
| `client` | `poll_interval_seconds` | `1.0`; finite positive number. |
| `client` | `token_file`, `ca_file` | Omitted; secret bearer token and HTTPS trust paths. |
| `client` | `tls_verify` | `true`. |
| `service` | `host`, `port` | `"127.0.0.1"`, `8080`. |
| `service` | `queue_capacity` | `100` waiting Runs, excluding the active Run; positive integer. |
| `service` | `request_max_bytes` | `16777216` (16 MiB), including multipart upload framing. |
| `service` | `token_file` | Omitted in the trusted local profile; otherwise a secret bearer-token file. |

## Filesystem project example

```toml
schema_version = 1
[project]
id = "my-project"
[definitions.pipelines]
training = "orchestration/kfp/compiled/training.yaml"
[execution]
work_directory = "work"
timeout_seconds = 600
[artifacts]
backend = "filesystem"
managed_root = "data/artifacts"
external_roots = ["data/external"]
[reuse]
scope = "global"
```

Generated outputs use `data/artifacts/PIPELINE/RUN/TASK/ATTEMPT_UUID/OUTPUT`.
See [artifact layout](artifacts.md#materialization-and-publication) for imports,
recovery metadata and S3 placement. Choose either
`managed_root` or `root`; specifying both is an error even across configuration
and environment overrides. Relative paths resolve against the project root.
Keep this directory separate from external data, state, metadata and execution
work. Changing it does not move existing stored artifacts or rewrite their URIs.

The complete runnable [quickstart configuration](../examples/quickstart/.dockflow-pipelines.toml)
uses a prepared local image. The [service configuration](../deploy/dockflow.example.toml)
demonstrates S3 and container-visible paths.

## Environment overrides

Prefix every suffix below with `DOCKFLOW_PIPELINES_`. Only the listed mappings
are interpreted; definitions and input root lists remain in TOML.

| Suffix | Setting |
| --- | --- |
| `CONFIG` | Configuration-file selection. |
| `ENDPOINT` | `client.endpoint` |
| `PROJECT_ROOT` | `project.root` |
| `STATE_DIRECTORY` | `state.directory` |
| `METADATA_BACKEND`, `METADATA_DIRECTORY` | `metadata.backend`, `metadata.directory` |
| `WORK_DIRECTORY` | `execution.work_directory` |
| `TIMEOUT_SECONDS`, `SHUTDOWN_GRACE_SECONDS` | Corresponding `execution` fields. |
| `CPU_LIMIT`, `MEMORY_LIMIT_BYTES` | Corresponding `execution` fields. |
| `IMAGE_PULL_POLICY` | `images.pull_policy` |
| `ARTIFACTS_BACKEND`, `ARTIFACTS_ROOT` | `artifacts.backend`, `artifacts.root` |
| `ARTIFACTS_MANAGED_ROOT` | `artifacts.managed_root` |
| `S3_ENDPOINT`, `S3_BUCKET`, `S3_PREFIX` | `artifacts.endpoint`, `artifacts.bucket`, `artifacts.prefix` |
| `S3_TLS_VERIFY`, `S3_ALLOW_INSECURE_HTTP` | Corresponding `artifacts` fields. |
| `REUSE_SCOPE`, `REUSE_SCOPE_KEY` | `reuse.scope`, `reuse.scope_key` |
| `HOST`, `PORT` | `service.host`, `service.port` |
| `QUEUE_CAPACITY`, `REQUEST_MAX_BYTES` | Corresponding `service` fields. |
| `POLL_INTERVAL_SECONDS` | `client.poll_interval_seconds` |
| `CLIENT_TOKEN_FILE`, `CLIENT_CA_FILE`, `CLIENT_TLS_VERIFY` | Corresponding `client` fields. |
| `SERVICE_TOKEN_FILE` | `service.token_file` |

Booleans accept case-insensitive `true` or `false`. Integer values are nonnegative
decimal strings before field-specific validation. Empty values fail except
`S3_PREFIX`. Provider credentials use standard AWS-compatible discovery such as
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, optional `AWS_SESSION_TOKEN` or a
selected `AWS_PROFILE`; do not put them in the project TOML. Registry credentials
belong to the Docker environment. Neither is automatically forwarded to tasks.

## Inspecting the configuration used by a Run

Use `dockflow pipelines --json runs show RUN_ID`, or
`GET /dockflow/v1/runs/RUN_ID`, to inspect `effective_configuration` captured
when the Run was admitted. CLI JSON places it under
`result.effective_configuration`; the API exposes it directly. Its `sources` map records the winning origin for
settings such as `execution.timeout_seconds`: `file`, `environment`, `option`,
`default` or `derived`. `config_path` records how the configuration file was
selected, including `discovery`. Paths derived from state or a legacy artifact
root are distinguished from explicit settings.

The snapshot retains the original values/origins when configuration changes.
Older Runs may have no `sources`; their provenance is unavailable. Token-file
paths can appear, but token contents, provider credentials and mounted file
contents are excluded. No additional configuration-inspection command is needed.

## Optional local policy

A policy file can constrain cache and retry safety without changing compiled
semantics:

```json
{
  "schema_version": 1,
  "definition_sha256": "THE_EXACT_ACCEPTED_DEFINITION_SHA256",
  "tasks": {
    "generate": {"cache_safe": false},
    "summarize": {"scope": "keyed", "scope_key": "development", "retry_safe": true}
  }
}
```

Use the accepted definition's exact byte hash and qualified task paths. Unknown
tasks/fields and stale hashes fail. `cache_safe = true` cannot override compiled
cache disablement. `retry_safe = true` declares the component safe to repeat; it
does not invent a retry count absent from its compiled policy. See
[artifacts and reuse](artifacts.md).

## Task publication directories and configuration files

Trusted local/service configuration can mount explicit files/directories into
component containers. This supports libraries such as Dockflow Artifacts:

```toml
[[execution.task_mounts]]
source = "data/published"
read_only = false

[[execution.task_mounts]]
source = ".runtime/publication.json"
target = "/etc/dockflow-artifacts/config.json"
```

Create these sources before running. Relative sources resolve from project.root;
omitted targets use the same absolute path. Read-only is the default. Targets
cannot overlap runtime mounts. The Docker daemon must see the same source paths.
Configuration stores paths/modes, never file contents. Keep secret files out of
source control. Changing mounted publication configuration is not a tracked data
change: disable reuse or change a declared pipeline input when changing its store.
