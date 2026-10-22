# Publication and integrity

Destinations are custom relative POSIX paths under a configured root. Preserve
the caller's filename and directory contents; do not add run/task/UUID/payload
segments. Run IDs, dates, versions and similar naming context belong to the caller.
Reject absolute destinations, empty/dot/dotdot segments, backslashes, control
characters, URI delimiters/encoding ambiguity and the reserved
.dockflow namespace (also reserve the legacy .dockflow-artifacts namespace). Reject symlinks and nonregular source entries.
Reject source/destination overlap and symlinked destination ancestry.

Inventory regular files with relative names, byte sizes and SHA-256. A file's
digest is SHA-256 of its bytes. A directory digest is SHA-256 of the canonical
sorted file inventory. JSON is UTF-8, sorted keys, compact separators and finite
numbers only. Empty files are supported; empty directories are rejected in this
initial portable contract. No filesystem permissions/ownership/timestamps are
part of artifact identity.

Publication identity includes destination, type, metadata and content inventory.
Write a durable reservation before payloads and a completion manifest last.
Only completed, verified contents may be returned for registration. Directory
publication is not an atomic object-store rename: partial bytes can exist before
completion. Importers are invoked only after successful completion.

Never overwrite different contents. Repeated identical publication is idempotent.
Concurrent identical writers converge; conflicting writers fail. Ancestor
namespace reservations exclude overlapping file/directory publications.
Interrupted identical publications may resume missing payloads; committed
publications with missing, changed or additional contents fail integrity checking.
Source mutation detected while reading/publishing fails before completion.
Immutable conditional writes are required, including on S3-compatible servers;
do not silently fall back to unconditional overwrite.

Control records live under .dockflow/dockflow-artifacts inside the artifact root, outside payload
directories. They are versioned and contain no credentials. Receipt metadata is
caller-owned JSON; library integrity fields remain separate. A successful
publication followed by task/importer failure can leave an unreferenced complete
artifact. Preserve it for retry; no automatic deletion or retention is promised.

The sibling `.dockflow/dockflow-pipelines` namespace belongs to the orchestrator;
publication records do not share its database or lifecycle. Reserve the full
`.dockflow` segment against user destinations and source inventory entries.
Legacy `.dockflow-artifacts` records require an explicit fresh root/reset before
publication or verification; fail before writing rather than ignore old claims.
Do not automatically move records or silently adopt existing payloads.

## Deterministic publication IDs

Expose `publication_id(*, component_name, component_version, parameters, inputs=None)`.
It returns the full lowercase SHA-256 digest of a versioned invocation descriptor,
not a backend artifact ID, output-content digest or native execution-cache key.
Component name/version are nonempty strings. Parameters and named input identities
are JSON objects. The caller supplies resolved defaults and every input that can
affect bytes, type, metadata or destination. Include exploration, pipeline name,
step number and step width when using the step policy below. Input identities
include immutable content fingerprints and any metadata observed by the component.
The caller versions the component implementation, wrapper and relevant runtime;
mutable image tags alone are not a sufficient component version.

The descriptor has keys `format` (`dockflow-publication-id-v1`), `component_name`,
`component_version`, `parameters` and `inputs` (default empty object). Encode it as
a recursive typed tree: null `["null"]`, boolean `["bool", value]`, integer
`["int", decimal-string]`, float `["float64", big-endian-IEEE754-hex]`, string
`["string", value]`, array `["array", typed-items]`, object
`["object", [[typed-key, typed-value], ...]]` with string keys sorted by Unicode
codepoint. Serialize compact UTF-8 JSON with ASCII escaping, then SHA-256.
Preserve numeric types, negative zero and array order; ignore object insertion
order. Reject nonfinite floats, integers outside ±(2^53−1), invalid Unicode,
non-string keys and non-JSON values. No implicit default filling, path reads,
clock/random values, environment inspection or backend requests occur.

Expose `fingerprint(source)` for explicit local file/tree content identities:
`{algorithm: "sha256", kind: "file"|"directory", value: digest}`. Reuse the
inventory/integrity rules above. Temporary staging locations are not identity;
relative names within directory trees are. Remote staging remains caller-owned.

Matching declared inputs produce the same ID; changed declared values produce
a different ID subject to SHA-256 collision resistance. This does not guarantee
deterministic business code. Different bytes/type/metadata at an existing path
still fail immutability checks. The ID helper never skips component execution,
queries manifests for compute reuse, or overrides a native cache.

## Exploration and step paths

Expose `step_path(filename, *, step_number, step_digits, component_name,
pipeline_name, publication_id, exploration_id="global")` as an optional
framework-independent policy:
`<exploration>/<pipeline>/step_<padded-number>__<component>__<publication-id>/<filename>`.
Require a positive integer step number and explicit integer width from 1 to 12
(reject booleans), a full lowercase SHA-256 publication ID, and safe single-segment
names. Zero-pad to the supplied minimum width; never truncate larger numbers.
Preserve filename/extension. Outputs of the same invocation can share the directory
with distinct filenames. Arbitrary publish/format_path paths remain supported.

The pipeline wrapper declares computational step order and computes width from
its total step count: `len(str(number_of_steps))`. Four steps use 1–4, twelve use
01–12, one hundred use 001–100. Importers are excluded. There is no fixed default
width, implicit counter, graph inspection or execution-order inference in this
library. The component wrapper supplies its component name and filenames.
Exploration defaults to global. Pipeline/exploration/step/width/version must be
actual component inputs when orchestrator cache isolation is required. The same
pipeline, context, step and complete inputs retain the same path on a cache hit;
changed inputs have another component directory under the same pipeline.
Different pipeline names isolate both path and execution context. Run IDs are
not added. Changing width as a pipeline grows is a declared destination/input
change and can invalidate otherwise reusable executions.
