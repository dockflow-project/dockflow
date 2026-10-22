# Security

Dockflow is currently an unreleased development project. There is no supported
stable release or published security maintenance window yet.

## Deployment boundary

Dockflow executes container images selected by pipeline authors. Use it for
trusted pipelines and users within one project. Access to run submission is
permission to execute workloads with the configured Docker executor; Docker
access and the privileged reference Docker-in-Docker service are powerful host
capabilities. Containers do not make this deployment a sandbox for hostile code.

The reference deployment binds its public ports to loopback. For access beyond
a trusted private environment, configure a service bearer token from a secret
file and terminate TLS at a reverse proxy. A token grants access to the whole
project; Dockflow does not provide separate user permissions or tenant isolation.
Keep the Docker socket and artifact-store credentials private.

Treat pipeline definitions, parameter values, artifact metadata, task logs and
outputs as retained project data. Do not put secrets in pipeline parameters,
compiled definitions or output metadata. A task can print anything it receives;
Dockflow cannot reliably identify arbitrary secrets in application logs.

See the [deployment guide](docs/deployment.md),
[configuration reference](docs/configuration.md) and
[persistence guide](docs/persistence.md) for service access, storage ownership and
backup behavior.

## Reporting a vulnerability

The selected confidential channel is **GitHub private vulnerability reporting**
on the [repository's Security page](https://github.com/dockflow-project/dockflow/security).
Use **Report a vulnerability** there when it is available. As part of making
the repository public, maintainers must enable private reporting and verify the
reporting option before announcing the preview. GitHub provides this feature for
public repositories; follow its [configuration instructions](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository).
The source checkout neither enables that setting nor proves it is configured.

If the reporting option is unavailable, a public request for a private contact
must contain no sensitive details. Do not publish credentials, private data or a
working exploit in a public issue.

A useful private report identifies the Dockflow version or source commit, affected
configuration, impact and minimal reproduction with synthetic data. Include
relevant logs only after removing tokens, credentials and private paths. Security
updates and supported versions will be documented here when releases exist.

## Certificate trust incident

The current source contains remediation for the October 2026 eMudhra/emSign
incident. Follow [certificate maintenance](docs/certificate-maintenance.md) to
upgrade existing environments and rebuild images. The initial 0.1.0 release
candidate was withdrawn from further publication; its tags and already uploaded
CLI remain immutable. Source fixes have not yet been released as packages/images.

## Dependency and image review

The workspace lock and immutable container-image references support repeatable
review; they do not establish that a dependency has no vulnerabilities. Release
preparation must review the exact Python environment, base/service images and
third-party notices. CI and local tests are not a security audit.
