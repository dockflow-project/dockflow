# Public API

All core names are exported by `dockflow_artifacts`. Imports perform no I/O.

| API | Contract |
| --- | --- |
| `Publisher(root, *, s3=None)` | Configure an absolute filesystem or S3-compatible root. Optional S3 SDK is loaded only for remote roots. |
| `Publisher.from_config(path)` | Explicitly read a schema-version 1 JSON config. See storage documentation for fields. |
| `publisher.publish(source, destination, *, artifact_type="system.Artifact", metadata=None)` | Publish a file or nonempty directory; return a completed `Publication`. Destination is relative to the root. |
| `publisher.verify(destination)` | Re-read the completion manifest and all payload bytes; return a `Publication` or raise an integrity error. |
| `format_path(template, **values)` | Expand simple named fields; substitutions must each be safe single segments. No conversion/format-spec expressions. |
| `step_path(filename, *, step_number, step_digits, component_name, pipeline_name, publication_id, exploration_id="global")` | Return `<exploration>/<pipeline>/step_<padded-number>__<component>__<publication-id>/<filename>`; explicit width 1–12 and safe single-segment names. |
| `publication_id(*, component_name, component_version, parameters, inputs=None)` | Full SHA-256 of a versioned, typed canonical invocation descriptor. Supply resolved defaults, context and all relevant inputs. No cache lookup. |
| `fingerprint(source)` | Explicit local file/tree fingerprint: `algorithm`, `kind`, `value`. Ignores staging location; includes relative tree filenames. |
| `Publication.to_dict()` | Return a detached JSON-compatible receipt. |

`Publication` fields: `uri`, `manifest_uri`, `digest` (SHA-256), `kind` (`file` or
`directory`), `artifact_type` (schema title) and `metadata` (caller JSON).

`ArtifactError` is the public base exception. `ConflictError` indicates a
reserved destination incompatible with this publication. `IntegrityError`
indicates mismatching/missing contents or invalid completion records. Ordinary
local permission/I/O errors may also propagate; remote errors omit credential
values. Publication never deletes or overwrites a conflicting payload.

Optional `dockflow_artifacts.kfp.importer_component(artifact_class, *,
metadata=None, reimport=False, name=None)` creates a callable KFP graph component
containing a standard typed importer. Call the factory outside the parent pipeline
definition, then call its result with `uri=STRING_OR_PARAMETER_CHANNEL` inside
the pipeline. Use that task's `.output` as a typed artifact input. `metadata`
is a static JSON object; `name` names the graph component. Authoring performs
no publication or payload verification. See [KFP integration](kfp.md).

Publication IDs preserve parameter types (including integer versus float and
negative zero), array order and Unicode strings; dictionary insertion order is
irrelevant. Values must be portable JSON: finite numbers, integers within
±(2^53−1), valid Unicode and string object keys. Include immutable input
fingerprints plus any metadata the component observes. Component versions must
cover implementation, wrapper and relevant runtime dependencies. Filenames are
selected separately so multiple outputs can share an invocation directory.

`step_digits` is computed by the pipeline as `len(str(number_of_steps))`.
`step_path` pads to that width and never truncates a larger step number. The
helper does not inspect a pipeline or count tasks. See the [usage example](storage.md).
The new step policy changes the earlier helper signature/layout; existing
publications stay intact but newly compiled wrappers use the new destinations.
