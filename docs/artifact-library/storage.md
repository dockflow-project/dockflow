# Publishing and storage

Constructing `Publisher` (including `from_config`) validates configuration locally.
It creates no storage client and performs no network credential discovery. The
S3 client and optional dependency are loaded on the first `publish` or `verify`
operation; install the `s3` extra before using those operations on object storage.


Construct `Publisher` with an absolute local directory/file URI or an
`s3://bucket/prefix` root. Install the `s3` extra for object storage. `minio://`
is also supported as a URI alias for native KFP deployments.

```python
from dockflow_artifacts import Publisher

publisher = Publisher(
    "s3://artifacts/custom",
    database={"backend": "postgresql", "dsn_env": "DOCKFLOW_DATABASE_DSN"},
    project_id="demo",
    s3={"endpoint_url": "http://object-store:8333", "region_name": "us-east-1"},
)
receipt = publisher.publish("model.json", "models/demo/v1/model.json",
                            artifact_type="system.Model")
```

Use the normal boto3 credential chain or explicit S3 constructor options.
For deployment, mount a JSON config read-only and call `Publisher.from_config`:

```json
{
  "schema_version": 2,
  "root": "s3://artifacts/custom",
  "database": {"backend": "postgresql", "dsn_env": "DOCKFLOW_DATABASE_DSN"},
  "project_id": "demo",
  "s3": {"endpoint_url": "http://object-store:8333", "region_name": "us-east-1"}
}
```

S3 options also accept `aws_access_key_id`, `aws_secret_access_key`,
`aws_session_token` and `verify` (boolean or CA path). Keep configurations
containing credentials outside source control. Never embed them in KFP YAML.
Unknown configuration fields are rejected.

Paths use safe relative segments of letters, digits, underscores, hyphens and
dots. Root containment, symlink and source-overlap checks apply. Files retain
their chosen names; directory trees retain relative filenames. Zero-byte files
are valid. Empty directories and nonregular files are not supported.

Reservations and completion manifests live in the SQL database. The artifact
root retains payloads, disposable staging and `.dockflow/storage.json`, a small
identity marker that binds database records to this store. Complete payloads are verified before their URI is returned. A directory
upload can have visible partial bytes before completion; consumers should only
receive successfully published URIs. Identical retries resume incomplete writes.
Conflicting bytes/types/metadata are never overwritten. Changed or missing
completed payloads cause `IntegrityError`; use a new versioned destination for
new contents.

S3 servers must support conditional `PutObject(IfNoneMatch="*")`. There is no
unsafe fallback. Individual S3 files are limited to 5 GiB in this first version.
Use a dedicated prefix owned by this library, with credentials limited to it.
Filesystem stores require POSIX hard-link support. Other writers must not mutate
published contents or control records.

Back up the database and payloads, including the identity marker, together. The library performs no
automatic retention or garbage collection. A successful publication followed by
task failure may remain unreferenced; retrying the same publication is safe.

## Deterministic exploration paths

Use `publication_id` and `step_path` when each invocation should have a stable
location. The wrapper receives the context and component version from its pipeline:

```python
from dockflow_artifacts import fingerprint, publication_id, step_path

# The pipeline computes this from its ordered computational steps (importers excluded).
step_digits = len(str(12))  # A twelve-step pipeline uses 01 ... 12.
parameters = {
    "exploration_id": "global", "pipeline_name": "training",
    "step_number": 3, "step_digits": step_digits, "seed": 42,
}
identity = publication_id(
    component_name="train", component_version="train-v1-runtime-v1",
    parameters=parameters,
    inputs={"dataset": fingerprint("training.json")},
)
destination = step_path(
    "model.json", exploration_id=parameters["exploration_id"],
    pipeline_name=parameters["pipeline_name"], step_number=3,
    step_digits=step_digits, component_name="train", publication_id=identity,
)
# global/training/step_03__train__<full-64-character-id>/model.json
receipt = publisher.publish("model.json", destination, artifact_type="system.Model")
```

`training.json` and `model.json` must exist. Same context, version, parameters
and input contents give the same ID/path. Different inputs yield a different
component directory beneath the pipeline. Pass every resolved parameter that
can affect the output, and version the script, wrapper and relevant runtime.
Include input metadata if the component observes it. The library does not infer
these dependencies. `exploration_id` defaults to `global` in the path helper.

The pipeline owns its name, step order and width, computed from its total step
count; the component wrapper owns its component name and filenames. No run IDs
or randomness are added. Width changes at ten, one hundred, etc. are explicit
input/destination changes. `format_path` and arbitrary relative destinations
remain available for other policies.

Execution caching belongs to KFP/Dockflow: a hit skips execution and keeps the
original URI. These helpers do not add a compute cache. Without a cache hit, the
component runs; identical publication is then idempotent. Different bytes/type/
metadata at the same deterministic destination still fail rather than overwrite.
This catches undeclared dependencies and nondeterministic outputs. Use a new
exploration to request a separate execution context.

## Database configuration

`Publisher(root)` with a filesystem root defaults to `.dockflow/state.sqlite`
under the root's parent directory. For a project whose artifact root is
`artifacts/`, that is the project's `.dockflow/state.sqlite`. The default project
ID is `default`. Pass the same database and project ID as Pipelines when sharing
its state; the library does not discover Pipelines configuration automatically.

Use `database={"backend": "sqlite", "database": str(database_path.resolve())}`
for an explicit local database, or the PostgreSQL configuration above across
isolated hosts. PostgreSQL requires `dockflow-artifacts[postgresql]`; set the
named DSN environment variable through deployment secrets. Remote artifact roots
require explicit database configuration. Constructor database paths are absolute;
relative paths in a JSON config resolve against that config's directory.

All writers sharing a publication root must use the same database and project ID.
For containerized SQLite publishers, mount the containing database directory so
its WAL/SHM companions are shared as well. Use PostgreSQL across isolated hosts.
The shared `dockflow-database` package supplies both backend implementations.
Configuration and imports open no connections. Publishing initializes a fresh
schema; verification opens an existing read-only snapshot. Completion records
remain immutable. `manifest_uri` is now a logical `dockflow://` database address;
use `publisher.verify(destination)` to retrieve and check the publication.

Pipelines backup includes these records and bytes when publication uses its
managed root and project. Its backup tool rejects projects containing records
for additional roots: back up those roots and the database together using an
offline provider snapshot. Keep publishers idle during filesystem backups.
Older sidecar layouts and database schemas require fresh disposable state;
there is no automatic migration or deletion.


S3 uses maintained `certifi` trust by default. An explicit `verify` certificate
path takes precedence; when omitted, the SDK's `AWS_CA_BUNDLE` or profile
`ca_bundle` remains supported. `verify=true` selects certifi explicitly.
Update custom bundles independently; see [certificate maintenance](../certificate-maintenance.md).


Filesystem publication flushes each payload and every containing directory up
through the existing filesystem ancestors before recording SQL completion. This
covers newly created roots and identity-marker entries. An identical retry also
flushes existing payload/identity entries, so a previous synchronization failure
cannot be acknowledged without retrying the durable boundary. Synchronization
errors fail publication; verified payloads can be retained for an identical retry.
