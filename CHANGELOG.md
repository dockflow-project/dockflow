# Changelog

## 0.1.1

- Address the eMudhra/emSign CA incident in Python, uv, gRPC, S3 trust defaults,
  and the reference container stack.
- Check actual certificate bundles, including embedded pip/ensurepip and
  cross-signing roots, during CI and service image qualification.
- Preserve explicit custom S3 CA settings and existing registry storage format.
- Publish through the official PyPA v1.14.3 Trusted Publishing action; remove
  the custom publisher wrapper. Keep unchanged specification baseline provenance
  without moving existing tags.

The 0.1.0 publication stopped after the CLI upload. Its vulnerable service
candidate is withdrawn. Version 0.1.1 is the coordinated replacement; publication
remains subject to exact-candidate approval.

## 0.1.0

Initial coordinated release of `dockflow-cli`, `dockflow-pipelines` and
`dockflow-artifacts`. All packages require Python 3.12 or newer; the tested
interpreter matrix is 3.12 and 3.13.

- Execute the supported compiled KFP 2.17 pipeline profile locally with Docker
  or through a persistent REST/browser service without Kubernetes.
- Inspect durable runs, logs, artifacts, lineage and reuse; upload immutable
  pipeline versions through the supported KFP client API subset.
- Publish immutable files and directories to caller-selected filesystem or S3
  paths, and register them through typed KFP importers with the artifact library.
- Install the remote CLI without Docker, KFP or MLMD dependencies.

The qualified execution/service target is Linux x86-64 with Linux containers.
Base-package installation is separately checked on Linux, macOS and Windows.
Native ARM64 execution and Docker Desktop deployments are not qualified by this
release. This is a bounded initial milestone, not full KFP backend parity;
unsupported constructs are rejected. See [compatibility](docs/compatibility.md)
and the runtime `dockflow pipelines capabilities` response.

KFP extras require the documented urllib3 override; ordinary pip resolution
retains upstream KFP's older exact pin. Follow [installation](docs/installation.md).

There is no earlier published Dockflow package release to migrate from.
Experimental source-checkout state is not promised an automatic migration;
back up retained state before switching an existing deployment.
