# Product and boundaries

The Python distribution is dockflow-artifacts; the import package is
dockflow_artifacts. Support Python 3.12 and 3.13 on POSIX for filesystem
publication. Keep the standard-library core independent from Dockflow, KFP,
cloud SDKs and framework-global state. Optional s3 and kfp extras own their
dependencies, imported only when used.

Public API: Publisher, Publication, format_path, step_path, publication_id, fingerprint, ArtifactError,
ConflictError and IntegrityError. Publisher accepts explicit root/configuration, publishes a
local regular file or nonempty directory tree, verifies an existing publication,
and returns a serializable receipt. Publication exposes uri, manifest_uri,
digest, kind, artifact_type and metadata. No automatic reads or writes at import.

Business components operate on local directories. A caller/wrapper owns input
staging, invocation, output selection and publication. Components need not import
this package or know pipeline names, remote stores, path templates or KFP.
Wrappers can use a caller-supplied relative destination; path formatting is
explicit and rejects missing variables and unsafe substitutions.

This library owns immutable contents and publication receipts, not a pipeline
database, task scheduler, model registry service or authorization service.
No silent global configuration, background thread, telemetry or cleanup daemon.
