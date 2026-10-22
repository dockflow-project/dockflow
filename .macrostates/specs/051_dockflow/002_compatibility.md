# Python and platform compatibility

## Python baseline and default

All first-party distributions target standard CPython 3.12 as their minimum
supported interpreter. Shared and tool code must remain compatible with 3.12;
features introduced later cannot be unconditional requirements. Declare the
minimum in package metadata and configure language/type-checking tools for it.
Do not add an arbitrary upper Python bound solely because a newer interpreter
has not been tested; record a demonstrated incompatibility explicitly.

Python 3.13 is the default for the application development environment and the
Dockflow service container. Pin a tested patch/image identity in implementation
configuration and keep it maintained. A 3.13 default does not raise the 3.12
minimum. The separate specification-tool bootstrap environment is not the
application environment.

The initial required Python qualification matrix is 3.12 and 3.13. Check newer
stable versions in exploratory CI when practical; add them to advertised support
only after relevant dependency, package, CLI, and execution tests pass. The CLI
may qualify a newer interpreter before Pipelines, provided the combined
installation is documented and tested on their overlapping supported versions.
Task-image runtime constraints belong to Pipelines and are separate from the
Python runtime used by Dockflow itself.

## Initial OS and architecture targets

These are intended qualification targets, not claims of completed validation:

| Surface | Initial target |
| --- | --- |
| Shared CLI and Python package installation | Vendor-supported Linux and macOS on x86-64 and ARM64; Windows 11 on x86-64. |
| Dockflow execution/service images | Linux containers for `linux/amd64` and `linux/arm64`. |
| Native reference deployment | Linux with Docker Engine and Compose v2; Ubuntu 24.04 LTS is the initial reference host. |
| Desktop development deployment | Supported macOS with Docker Desktop on Intel or Apple silicon; Windows 11 x86-64 with Docker Desktop's WSL2 Linux backend. |

CLI portability does not promise native Windows or macOS task execution: the
specified stack runs Linux containers. Native Windows containers, Windows ARM64,
32-bit interpreters, alternative Python implementations, and emulation-only
execution are outside the initial qualified matrix.

Before advertising a platform, verify the relevant installation, help, plugin,
filesystem, and process behavior there. Before advertising a deployment target,
run the Pipelines smoke/acceptance checks on that host/backend. Native Linux
results do not qualify Docker Desktop automatically. Record exact host, Python,
Docker/Compose, and architecture versions in release evidence.

Publish first-party service images for both Linux architectures only after
validating them. All required service and task images must have a suitable
architecture variant. Cross-platform build success or emulation alone is not
evidence of native execution support; emulation remains an explicit opt-in.

## Annual support review and implementer notification

Review the Python and platform policy at least every twelve calendar months.
The initial policy-adoption date is 2026-10-15, and the first annual review is due
on 2027-10-15. Keep the dates and completed-review evidence in
[compatibility-review.yaml](../../implementation/compatibility-review.yaml).
Policy adoption is not a completed runtime compatibility review.

At session startup, before release preparation, and when a proposed dependency
change affects support, the implementer must check the review record. If the
current date is on or after `next_review_due_on`, or the record is missing or
inconsistent, notify the definer that review is due and ask them to perform or
authorize it. Explain the current matrix, relevant Python/OS support deadlines,
and dependency or qualification gaps. Avoid repeating the same unresolved
notification on every microprompt within one session.

Notify the definer earlier when a supported interpreter/OS approaches the end of
upstream security support or a required dependency can no longer support the
declared matrix. Assess newer Python releases and useful features during review;
do not drop older versions or adopt newer requirements automatically.

Record a completed review only after its outcome is confirmed by the definer:
include its date, a link to the owning workflow/review evidence, and a next due
date no later than twelve months afterward. Do not advance a due date merely to
clear an alert. Independent authorized work may continue while review is pending;
release preparation must surface an overdue review and obtain its disposition.

## Upstream references

- [Python support lifecycle](https://devguide.python.org/versions/)
- [Docker Desktop for macOS](https://docs.docker.com/desktop/setup/install/mac-install/)
- [Docker Desktop with WSL2](https://docs.docker.com/desktop/features/wsl/)
- [Docker multi-platform images](https://docs.docker.com/build/building/multi-platform/)
