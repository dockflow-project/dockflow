# Local execution and service deployment

## Two installation surfaces

Direct CLI execution runs installed Python core code with KFP DockerRunner and a
selected local Docker daemon. It starts no HTTP service or Compose project.
Filesystem artifacts and MLMD/SQLite need no additional service containers.
Prepare component images and compile definitions before invocation.

Publish a generic service image at
ghcr.io/dockflow-project/dockflow-pipelines under the shared application release
policy, plus a reference compose.yaml and safe .env.example. Users supply
configuration and persistent data and may mount configured compiled definitions
or register them through the KFP upload API without rebuilding the Dockflow image.
Custom component images remain independent images. Publication
names/permissions and exact image digests still require release qualification.

The image contains Pipelines runtime, HTTP service and S3 adapter dependencies,
not a consuming project's computations or a Docker daemon. Run the API on
0.0.0.0:8080 inside the container; publish host ports to 127.0.0.1 by default.
The image may connect to explicitly configured providers; Compose supplies the
complete default wiring.

## Default Compose topology

Use a single-machine Compose stack:

| Service | Responsibility |
| --- | --- |
| dockflow | API, single owner/queue, isolated execution worker and storage/metadata integration. |
| docker-engine | Dedicated Docker-in-Docker daemon for dynamic task containers. |
| minio | Default S3-compatible artifact provider with persistent object data. |
| registry | Local image registry for externally prepared component images. |

SQLite lives in the Dockflow state volume; no separate database container is
needed initially. External MLMD SQL backends, beginning with a qualified MySQL
profile, may be added without changing artifact/run semantics. PostgreSQL and
other database images are not advertised merely because upstream documents them.

Artifact backend and execution mode are independent. A persistent service may
use filesystem artifacts on an explicitly mounted persistent directory and
omit the S3 provider. Remote CLI clients select that service explicitly; artifact
paths and `file://` inputs resolve in the service namespace. This does not
require an example-specific service image or a second project identity. Direct
CLI/service alternation on one logical store is allowed only under the same
exclusive ownership contract and compatible configured storage/executor paths;
a live service remains the writer and clients mutate through its API.

Compose manages persistent services; DockerRunner creates task containers
dynamically in the inner daemon. A component image may serve multiple components/
commands; no one-image-per-task rule applies. Do not describe task containers as
Compose services or assume compose down stops them.

The conventional privileged DinD daemon is an explicit local-deployment exception
to non-root service preferences. This profile runs trusted workloads and is not
a security boundary for hostile code. The normal Dockflow service runs non-root
with the required volume/socket ownership. Never mount the host Docker socket
into the service or tasks, expose the inner daemon over TCP, or forward its socket
to component containers.

## Volumes, paths and daemon persistence

Mount dockflow-execution at /execution in both dockflow and docker-engine, at the
same path. KFP requests mounts resolved in the daemon filesystem; Docker-managed
named volumes avoid a prescribed physical-host directory. Configure each Run's
pipeline root below /execution/runs/<run-id> and any KFP workspace explicitly
below /execution/workspaces/<run-id>. No private temporary workspace is allowed.

Mount docker-socket into both services at /docker-socket and use
DOCKER_HOST=unix:///docker-socket/docker.sock with explicit ownership/permissions.
Keep engine state private to docker-engine. Persist all state required by the
pinned engine backend, including separate containerd storage if necessary;
never share host-engine data directories.

Use separate named volumes: dockflow-state for control state/SQLite,
dockflow-execution for work/staging, docker-state for /var/lib/docker,
docker-containerd for /var/lib/containerd, artifacts for the artifact provider's
data/metadata, and registry-data for /var/lib/registry. The shared socket remains
docker-socket. These labels do not change the container runtime paths above.
The artifacts volume contains managed imports and generated artifact payloads
alongside the selected provider's metadata. Mount configuration and any file-backed definitions read-only;
API-uploaded definitions persist in control state, not in a mutable configuration
mount or the container image. External file inputs
are explicit read-only mounts. Component code/dependencies reside in their images,
not host source mounts. KFP's shared-root mounting alone does not guarantee
per-task filesystem isolation.

## Networking and image provision

The inner engine pulls component images into its own cache; host-engine images
are not implicitly visible. The build/push preparation remains outside Dockflow.
Honor the configured pull policy and actual digest/platform recording.

A consuming project's deployment can build/tag/push its component images into
the configured registry, wait for Dockflow readiness, and use the official KFP
client's pipeline/version upload methods to register compiled definitions. It
then executes by the returned pipeline/version IDs. This preparation belongs to
the consuming project; Dockflow neither builds/pushes images nor imports project
Python. The running orchestrator remains the unmodified generic service image.
No project-specific long-running service or source bind mount is necessary.
Registry image publication and pipeline-definition registration are separate
operations; registration alone does not prove an image is present or runnable.

Persistent services share a Compose network. Nested task containers do not
automatically join it. Test route and DNS to every service a task explicitly
needs; never pass an outer network name to the inner daemon assuming equivalence.
Prefer owner-side artifact transfer so ordinary tasks need no MinIO credentials.

Use configurable endpoints and explicit TLS/trust. A plain-HTTP development
registry exception is restricted to its named local endpoint. MinIO HTTP access
must be explicitly enabled for that configured development endpoint. Use no
machine-specific IP addresses or credentials in committed examples.

## Operations and acceptance

Service startup validates schema/provider configuration, project identity,
ownership, control-store compatibility, Docker access and recovery. Readiness
remains false until reconciliation completes; liveness is process health.
Dependency health conditions/readiness checks must not run computations.

Loading configuration and package installation never create a daemon, build/push
images, run Compose or implicitly reset persistent state. Explicit startup may
initialize absent owned state/storage under its documented initialization policy;
it must not overwrite incompatible state. Use deployment-provided credentials,
with no baked-in secrets.

On shutdown stop admission, preserve queued Runs, terminate/reconcile active
inner tasks according to [Execution](005_execution-and-lifecycle.md), and persist
logs before cleanup. Ordinary shutdown/recreation preserves volumes. Destructive
reset is an explicit separate operation listing the data it removes.

The reference smoke test uses KFP client upload/version registration followed by
REST submission, registry images, multi-step
parameter/file/directory passing, S3 transfer, retained logs, failures,
interruption, service recreation and persistence. Qualify Linux native and
Desktop backends separately; cross-building or emulation does not establish native
support. Multi-node, cloud execution, Kubernetes and native Windows containers
remain outside the initial deployment profile.

The image's base must satisfy the qualified runtime dependencies. MLMD 1.21
Linux wheels require glibc 2.39 on x86-64; use an Ubuntu 24.04-based qualification
candidate instead of assuming every Python slim image works. Linux ARM64 needs a
reproducible MLMD source-build qualification before publication.
[Review and qualification](012_review-and-qualification.md) records those gates.
