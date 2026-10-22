# Certificate maintenance

[Documentation index](README.md) · [Installation](installation.md) · [Security](../SECURITY.md)

The October 2026 eMudhra/emSign incident compromised intermediate certificate
keys. Clients retaining the affected trust paths can accept forged HTTPS
certificates. The [Python security announcement](https://discuss.python.org/t/information-for-python-users-regarding-emudhra-emsign-ca-certificate-security-incident/109576)
requires updated package tools as well as application dependencies.

## Existing Python environments

Update the host operating system's certificate package through its supported
updater. Dockflow does not replace the host OS store or organization-managed
certificate bundles. Updating a checkout does not patch other virtual
environments, Docker daemons or component images.

Use uv **0.13.5 or newer**: 0.13.4 fixes uv's own trust store, while 0.13.5 also
selects patched managed Python builds. Existing installations can bootstrap pip
with the wheel and SHA-256 published by Python:

```bash
python -m pip install 'pip @ https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70'
python -m pip install --upgrade 'uv>=0.13.5' 'certifi>=2026.10.19'
```

Run this in each environment that contains pip. For uv without pip, use
`UV_SYSTEM_CERTS=true uv self update` only after the host certificate store is
updated. Never disable TLS verification to bootstrap an update.

For this repository, recreate the managed interpreter and synchronize:

```bash
uv python install --reinstall 3.13.17
uv sync --locked --all-packages --all-extras
uv run python tools/check_ca_trust.py --runtime
```

Python 3.13.17 includes patched pip **26.2.2** in `ensurepip`. Upgrading only the
installed pip does not update the wheel used to seed future environments.
For Python 3.12, use uv's refreshed managed build and re-create affected
virtual environments. gRPC requires **1.84.1** or newer; its certificate store
is separate from certifi. These floors are checked in the workspace and declared
by the affected optional package dependencies.

The offline check rejects the disclosed roots in certificate subjects, including
the AAA cross-sign. Local checks cover Dockflow's effective certifi/gRPC trust
and installed or embedded pip. `--system` additionally checks the Linux system
bundle. `--all-bundles` also checks dormant botocore data: Dockflow uses certifi
for S3 by default, while direct third-party SDK callers can choose another bundle.

Explicit S3 certificate paths and the artifact library's AWS environment/profile
CA settings remain available. Their owner must update those bundles. Public
servers chaining solely to removed roots need replacement certificates.

## Rebuild containers

After updating the source, rebuild the reference stack without cached package
layers, then recreate services. These commands preserve named data volumes:

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml build --pull --no-cache
docker compose --env-file deploy/.env -f deploy/compose.yaml up -d --force-recreate --wait
uv run python tools/check_ca_trust.py --image dockflow-pipelines:development
uv run python tools/check_ca_trust.py --system-image dockflow-docker-engine:ca-fixed
uv run python tools/check_ca_trust.py --system-image dockflow-registry:ca-fixed
```

Substitute the service image name if `DOCKFLOW_IMAGE` is configured. The service
image checks system, certifi, gRPC, botocore and pip/ensurepip bundles. Its dormant
botocore fallback bundle is aligned with certifi as well. Executor and registry
builds refresh both aggregate certificates and hashed certificate directories.
The registry remains on its existing major and storage format.

Rebuild component images separately and load/push them to the execution engine.
Dockflow cannot change the Python or trust stores inside arbitrary task images.
The repository quickstart now uses the patched Python base.

## Release status

The original 0.1.0 image candidate failed this check and must not be published.
Only the CLI was uploaded before publication stopped. Existing tags and files
remain unchanged; these source fixes need a new reviewed release candidate.
The publishing image preserves PyPA's OIDC and PEP 740 attestations with patched
Python, pip, certifi and sigstore. No package uploads occur during these checks.
