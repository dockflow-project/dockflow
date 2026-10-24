# Configuration and storage

Publisher(root=...) accepts an absolute filesystem path, file URI or S3-compatible
URI (s3://bucket/prefix; minio:// is an explicit alias for KFP deployments).
The root is an ownership boundary, not a sandbox against other local processes.
Filesystems require hard-link/atomic-create semantics. Object stores must support
conditional PutObject with If-None-Match. Initial S3 objects are limited to 5 GiB
per file; do not claim conditional multipart support.

Explicit JSON configuration is supported by Publisher.from_config(path), with
schema_version=2, root, optional project_id and database, and optional s3 fields endpoint_url, region_name,
aws_access_key_id, aws_secret_access_key, aws_session_token and verify. Unknown
fields, credential-bearing root/endpoint URIs and invalid types fail early.
Default SDK credential discovery is allowed when explicit keys are absent.
Do not print configuration secrets or embed them in compiled definitions,
receipts, error messages or ordinary logs. A secret config file can be mounted
read-only by the deployment. Filesystem writes and network calls occur only
when explicitly publishing or verifying. Construction, including `from_config`,
validates local configuration without creating an SDK client or resolving network
credentials. Optional S3 imports/client creation are deferred until storage is
used; a missing extra then produces an actionable installation error.

The caller supplies endpoint/credentials independently of artifact URI: a URI
never selects its own endpoint. Native KFP consumers and Dockflow importers must
be configured to reach the same store. file:// references mean the runtime's
filesystem, not an automatic host mount. Container storage mounts and secret
delivery belong to deployment, not the business component.

The publication root can share a disk or bucket with an orchestrator, using a
distinct prefix to avoid ownership conflicts. Back up payloads and the SQL database together. The caller owns retention and access permissions. Normal
Dockflow managed-store cleanup does not own these external references.

## SQL publication state

Publisher accepts `database` as the common Database instance or a connection
configuration: `{backend: sqlite, database: <absolute-path>}` or
`{backend: postgresql, dsn_env: <environment-variable-name>}`. Only the environment
variable name is persisted; credentials/DSN values must never enter receipts or
errors. Install `dockflow-artifacts[postgresql]` for the PostgreSQL driver.
Construction validates options without opening a database connection.

For filesystem roots, omitting database selects `.dockflow/state.sqlite` beside
the artifact root (under its parent directory). Remote roots require explicit
database configuration. `project_id` defaults to `default`; callers integrating
with Pipelines pass its project ID and `[state]` connection explicitly. Resolve
relative SQLite paths in JSON configuration against the config file directory;
constructor paths must be absolute and SQLite state must remain outside the
artifact root. Database initialization occurs only on publish.
Verification is read-only and never initializes missing state.

Both backends use the same schema and immutable-record repository. PostgreSQL
publication transactions acquire the project maintenance gate; backup/restore
excludes publishers as well as coordinators. Back up the project database and
all owned artifact roots together, including each identity marker. The single-root Pipelines backup tool refuses projects with records for additional
roots; those deployments require an offline provider snapshot covering the database
and every root. Keep publishers idle during backup.
