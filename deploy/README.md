# Reference Docker Compose service

[Documentation index](../docs/README.md) · [Deployment concepts](../docs/deployment.md)

This Linux x86-64 development profile runs the generic non-root Dockflow image,
a dedicated privileged Docker-in-Docker engine, MinIO and a local registry.
The service includes the browser UI and API explorer. SQLite/MLMD are stored
with control state; no separate database container is required.

Run all commands below from the repository root. You need Docker Compose,
Buildx, access to the pinned build dependencies, and the prepared Python
environment if you use the CLI.

## Prepare once

```bash
cp deploy/.env.example deploy/.env
cp deploy/dockflow.example.toml deploy/dockflow.toml
mkdir -p deploy/definitions deploy/inputs
```

Edit `deploy/.env` to choose local MinIO credentials. Edit `deploy/dockflow.toml`
to set a stable project ID. Keep its bucket equal to `MINIO_BUCKET` in `.env`;
Compose interpolation does not rewrite TOML strings. Choose an unused
`DOCKFLOW_PORT` if another service owns host port 8080.

To try the repository's quickstart pipeline, copy its compiled definition:

```bash
cp examples/quickstart/orchestration/kfp/compiled/statistics.yaml deploy/definitions/statistics.yaml
docker build -t dockflow-quickstart-components:v1 examples/quickstart
```

Add this entry to the existing `[definitions.pipelines]` table in
`deploy/dockflow.toml`:

```toml
statistics = "/definitions/statistics.yaml"
```

Alternatively keep the table empty and register definitions through the
[upload API](../docs/api.md#kfp-client-compatible-adapter) or browser after startup.
The generic service needs compiled contracts and prepared images, not project
Python source.

## Build and start

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml build
docker compose --env-file deploy/.env -f deploy/compose.yaml up -d --wait
```

The reference MinIO image is built from the pinned upstream source archive in
[Minio.Dockerfile](Minio.Dockerfile), with its license retained. It is a local
development build, not a published Dockflow-maintained upstream container.
The first build needs network access and may take time. Existing compatible
images can be reused; `DOCKFLOW_IMAGE` selects the service image name.

`initialize` sets shared volume ownership to `10001:10001`; `bucket` creates the
configured bucket if absent. Both exit after completion. The other four services
remain running.

Load the quickstart component image into the inner engine:

```bash
docker image save dockflow-quickstart-components:v1 | \
  docker compose --env-file deploy/.env -f deploy/compose.yaml exec -T docker-engine \
  docker --host=unix:///docker-socket/docker.sock image load
```

The host-built image is not automatically in that engine. For registry-based
deployment, use image names reachable from the inner engine; it resolves the
included registry as `registry:5000`, while the host reaches its loopback port
`127.0.0.1:5001`. The engine explicitly allows that local HTTP registry.

## Use

```bash
curl --fail http://127.0.0.1:8080/health/ready
dockflow pipelines --endpoint http://127.0.0.1:8080 run statistics
dockflow pipelines --endpoint http://127.0.0.1:8080 runs list
```

Open `http://127.0.0.1:8080/ui/` for pipeline/run inspection or
`http://127.0.0.1:8080/dockflow/v1/docs` for API documentation. Substitute the
chosen host port in these URLs when changing `DOCKFLOW_PORT`.

This Compose project has its own state and artifacts. It does not automatically
share the direct quickstart's local history. To design one shared repository-backed
service from the outset, follow [repository-backed storage](../docs/deployment.md#repository-backed-storage).

## Inspect and stop

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml ps
docker compose --env-file deploy/.env -f deploy/compose.yaml logs -f dockflow
docker compose --env-file deploy/.env -f deploy/compose.yaml down
```

Finish or explicitly cancel active Runs before planned shutdown. `down` preserves
named volumes. `down --volumes` is a destructive reset of history, artifact
provider data, registry images and inner-engine state; it is not the normal stop
command. See [operations](../docs/operations.md) and
[backup/restore](../docs/persistence.md#backup-and-restore).

## Mounts and volumes

`DOCKFLOW_CONFIG`, `DOCKFLOW_DEFINITIONS` and `DOCKFLOW_INPUTS` are host bind
source paths relative to `deploy/`. Their container paths are
`/config/dockflow.toml`, `/definitions` and `/inputs`. Use those container paths
in TOML. Source mounts are read-only; register external `file://` inputs beneath
the configured `/inputs` allowed root.

| Volume label | Contents / container path |
| --- | --- |
| `dockflow-state` | Catalogs, compiled snapshots, Run history, logs, MLMD SQLite at `/state`. |
| `dockflow-execution` | Staged inputs/outputs and task work at `/execution`, visible to both owner and engine. |
| `docker-socket` | Inner daemon's socket at `/docker-socket`. |
| `docker-state` | Inner Docker state at `/var/lib/docker`. |
| `docker-containerd` | Inner containerd state at `/var/lib/containerd`. |
| `artifacts` | Managed imports and generated outputs plus MinIO provider metadata at `/data`. |
| `registry-data` | Prepared component image registry data at `/var/lib/registry`. |

Compose prefixes labels with its project name (default `dockflow-reference_`).
No host Docker socket or TCP daemon is exposed. Components receive staged files;
they do not inherit S3 credentials. Tasks needing network services require
explicitly tested routes; the inner task network is not automatically the outer
Compose network.

For an older deployment that used `control-state`, `execution-data`,
`engine-state`, `containerd-state` or `minio-data`, the corresponding current
labels are `dockflow-state`, `dockflow-execution`, `docker-state`,
`docker-containerd` and `artifacts`. Changing a label does not migrate data.
Stop owner/provider/engine, copy old volumes into their new counterparts while
unused, preserve permissions and retain originals until integrity checks pass.
The socket/registry labels are unchanged.

The provided service image targets Linux x86-64/Python 3.13 on Ubuntu 24.04.
The reference Compose topology is an operational example, not a claim of
qualification on every OS, CPU architecture or S3-compatible implementation.
