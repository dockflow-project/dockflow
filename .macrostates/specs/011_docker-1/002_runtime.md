# Runtime

Containers should expose clear runtime behavior and avoid hiding operational
state inside the image.

## Health checks

Long-running services should define a health check when the project has a
meaningful way to determine readiness or health.

Health checks should be lightweight, deterministic, and aligned with the service
behavior that operators or dependent services need to know.

Avoid health checks that require privileged credentials, expensive external
calls, or mutable side effects.

Batch jobs, one-shot commands, and short-lived tools may omit health checks when
health is already represented by process exit status.

## Environment variables and secrets

Use environment variables for non-secret runtime configuration when appropriate.

Do not use environment variables as a reason to expose secrets casually. Secrets
should be provided through the deployment environment's secret mechanism when
available.

Images should not require committed secret files to run. Example environment
files may be committed only when they contain placeholders or safe defaults.

## Volumes

Use volumes for runtime state that must persist beyond a container's lifecycle
or for explicitly mounted input/output locations.

Do not use volumes to hide required application code or dependencies that should
be part of the image.

Document expected volume paths in project-specific specifications or
implementation documentation when those paths are part of supported operation.

## Logging

Containers should log to standard output and standard error by default.

Applications should not require operators to inspect files inside a container to
understand normal logs.

Log rotation, retention, forwarding, and aggregation are usually deployment
concerns and should not be implemented by writing unmanaged log files inside the
container unless a project-specific specification requires it.

## Restart policy

Restart policy is normally a runtime or orchestration concern, not something
owned by the image itself.

Project-specific specifications or deployment configuration should define when
a service restarts automatically, when failures should remain visible, and when
a one-shot job should not be restarted.

Applications should use meaningful exit codes and graceful shutdown behavior so
restart policy can be applied safely by the runtime environment.
