# Contributing

Dockflow has an accepted initial implementation and pending security maintenance. Start with the
[specification entrypoint](.macrostates/specs/main.md) and the
[current implementation status](.macrostates/implementation/main.md).

For usage questions, first try the [documentation](docs/README.md) and
[self-contained quickstart](docs/quickstart.md). When reporting a defect, include
versions, a minimal compiled definition or reproduction, expected/actual behavior
and relevant redacted logs. Keep credentials and private datasets out of reports.
Security concerns follow [SECURITY.md](SECURITY.md).

## Local setup and checks

Use uv 0.13.5 or newer and patched Python for the separate specification-tool bootstrap below.
Application development uses a Python 3.13 default with 3.12 compatibility
under the [shared compatibility and review policy](.macrostates/specs/051_dockflow/002_compatibility.md).

```bash
uv venv .venv-macrostates --python 3.13.17
uv pip install --python .venv-macrostates/bin/python -r tools/macrostates/requirements.txt
.venv-macrostates/bin/macrostates info
.venv-macrostates/bin/macrostates check
```

On Windows, use the corresponding executables under
`.venv-macrostates\Scripts\`. Activation is optional when using explicit paths.

The check validates composition structure, package dependencies, and the
installed external package inventories. It does not prove application behavior,
specification completeness, or approval.

Install uv and use the locked workspace for application development:

```bash
uv sync --locked --all-packages --all-extras
uv run python tools/check_ca_trust.py --runtime
uv run ruff check packages tests tools
uv run ruff format --check packages tests tools
uv run ruff check examples/quickstart
uv run ruff format --check examples/quickstart
uv run pyright
uv run pytest -m 'not docker and not s3'
node --test packages/pipelines/tests/web/*.test.mjs
DOCKFLOW_TEST_DOCKER=1 uv run pytest -m docker
uv run --all-packages --all-extras python tools/generate_api_docs.py --check
uv build --all-packages --force-pep517
uv run python tools/version.py
uv run pre-commit install
```

The dependency-free frontend tests use Node.js 20 or later only as a development
tool. Node is not required to install, serve or use Dockflow.

The offline CA check also inspects gRPC and pip/ensurepip bundles, which package
advisory databases can miss. See [certificate maintenance](docs/certificate-maintenance.md).
CI audits the exported third-party lock without resolving a different environment.
Run the same check after dependency updates:

```bash
mkdir -p tmp/security
uv export --locked --all-packages --all-extras --no-emit-workspace --no-hashes --output-file tmp/security/requirements.txt
uvx --from pip-audit==2.10.1 pip-audit --requirement tmp/security/requirements.txt --no-deps --disable-pip
```

The current KFP/urllib3 override and its standalone-install instructions are in
[installation](docs/installation.md#kfp-dependency-override). Keep
`tools/runtime-overrides.txt` aligned with the root uv override. Auditing the lock
does not replace checking whether vulnerable features are reachable or testing
an upstream dependency override.

Docker tests execute real trusted task containers against the daemon selected by
the Docker SDK environment. Before running them, prepare their fixture image
from the same immutable base used by the quickstart (CI does this explicitly):

```bash
test_image=$(sed -n 's/^FROM //p' examples/quickstart/Dockerfile)
docker pull "$test_image"
docker tag "$test_image" python:3.13-slim
```

They require local socket access. API contract tests
also require the test runner's local thread/socket facilities. S3 unit tests use
a controlled provider fixture; provider integration needs a separately prepared
service. The reference Compose topology is described in [deployment](docs/deployment.md).
CI runs nonpublishing builds and tests. Do not treat native Linux
results as qualification of every intended OS or architecture.

The artifact library belongs to the same workspace, version policy and checks.
Its real S3 test uses a schema-version 1 publisher configuration (see
[storage configuration](docs/artifact-library/storage.md)) and creates/removes
only a unique qualification prefix inside that root:

```bash
DOCKFLOW_TEST_ARTIFACT_S3_CONFIG=/absolute/path/to/test-config.json \
  uv run pytest packages/artifacts/tests/test_s3_integration.py
uv run python tools/verify_packages.py
```

Keep test credentials outside source control. Package verification builds all
four distributions, checks standalone Artifacts imports without optional
dependencies, and rebuilds every sdist outside the checkout.

## Documentation and examples

Keep user instructions under [docs](docs/README.md) focused on how to use and
operate Dockflow. Internal decisions, workflows and qualification records belong
under `.macrostates/implementation`; temporary reviews belong under `tmp/`.
Examples must run from this repository without another private/sibling checkout.

The API reference is generated from `create_app(...).openapi()` without entering
the application lifespan, opening a store or starting infrastructure. After a
contract change, regenerate and review it:

```bash
uv run --all-packages --all-extras python tools/generate_api_docs.py
```

Keep the [quickstart](examples/quickstart/README.md) compiled definition in sync
with its KFP wrappers, and verify any changed tutorial commands using disposable
state. The standalone component scripts intentionally import no KFP or Dockflow.

## Browser qualification

The browser probe uses optional **Playwright 1.55.0** and its Chromium headless
shell. These are developer tools, not application/runtime dependencies. Install
the browser binary into your chosen Playwright cache:

```bash
uv run --all-packages --all-extras --with playwright==1.55.0 python -m playwright install chromium --only-shell
```

Prepare `python:3.13-slim` in the selected Docker engine before the fixture; it
never pulls an absent image. Start a new disposable fixture from the repository
root in one terminal:

```bash
uv run --all-packages --all-extras python tools/web_fixture.py --directory tmp/browser-project --port 0
```

The directory must not exist. The startup JSON reports its `endpoint`, selected
free port, `compiled_pipeline` path and `web-fixture-…` project identity. In
another terminal, substitute that actual endpoint for `FIXTURE_URL`:

```bash
uv run --all-packages --all-extras --with playwright==1.55.0 python tools/browser_smoke.py \
  --url FIXTURE_URL --definition tmp/browser-project/pipeline.json --output tmp/browser
```

The probe creates real task Runs and retained test records, records browser
assertions and screenshots under the output directory, and refuses a service
without the disposable `web-fixture-` identity prefix. Run it only against this
dedicated fixture, never an existing user service. For the authenticated journey,
start a separate fresh fixture with `--token-file PATH` and pass the same option
to the probe. Do not commit the token, fixture data or screenshots.

With at least one pipeline and Run present in the disposable fixture, verify
workspace sizing, background drag/cancellation, independent scroll regions and
preserved graph state using:

```bash
uv run --all-packages --all-extras --with playwright==1.55.0 python tools/graph_workspace_browser_smoke.py --url FIXTURE_URL
```

This probe performs read-only API requests. It projects long/nested graphs and a
running status only inside the browser to exercise layout and live refresh; it
does not modify stored definitions or execution records.

To check fixed list headers/footers, sticky columns, cursor/local pagination,
empty/error states and narrow layouts, use a disposable fixture containing all
catalog types and two Runs, one with more than 50 tasks. Register and run the
[scrolling example](examples/scrolling/README.md) alongside the ordinary fixture
Run, then run:

```bash
uv run --all-packages --all-extras --with playwright==1.55.0 python tools/list_workspace_browser_smoke.py --url FIXTURE_URL
```

This probe reads fixture records and projects additional cursor pages, consumer
rows and cleanup inventory only in the browser. It does not delete records/files,
submit executions or create a persistent storage scan.

For non-graph detail headers/tabs, independent body scrolling, long records,
keyboard/narrow layouts and refresh recovery, run the read-only detail probe
against a fixture containing component, artifact, Run, task and attempt records:

```bash
uv run --all-packages --all-extras --with playwright==1.55.0 python tools/detail_workspace_browser_smoke.py --url FIXTURE_URL
```

Long replies are projected only inside the browser. The probe opens and dismisses
the initial deletion dialog without planning/applying deletion, and verifies the
execution action that returns to the selected task in the graph.

For artifact Contents, start a fresh fixture with `--contents` to generate a
250,000-row CSV, JSON, PNG image, nested directory and text samples, then run:

```bash
uv run --all-packages --all-extras --with playwright==1.55.0 python tools/contents_browser_smoke.py --url FIXTURE_URL --output tmp/contents-browser
```

This probe reads real previews without changing records/files. It checks CSV
continuity/bounded responses, JSON precision/lazy batches, raster fit controls,
directory/history/empty/error states and narrow layouts. For an authenticated
fixture, pass the same `--token-file PATH` to fixture and probe. The S3 preview
integration tests use `DOCKFLOW_TEST_CONTENTS_S3_ENDPOINT` and standard test AWS
credentials, creating/removing only uniquely named disposable buckets.

For client-file upload and both ZIP modes, run the mutation probe only against a
disposable fixture (it registers four manual artifacts and leaves existing data):

```bash
uv run --all-packages --all-extras --with playwright==1.55.0 python tools/upload_browser_smoke.py --url FIXTURE_URL --output tmp/upload-browser
```

Pass the fixture's `--token-file PATH` when authentication is enabled. This checks
default Contents, nested directory/empty-folder previews, busy submission, invalid
ZIP recovery, file-type switching and desktop/narrow form layouts. Review and
discard optional captures; retain only anonymized receipts. Backend/API/CLI ZIP
and admission cases live in `test_artifact_uploads.py`; the opt-in S3 integration
also checks managed file/archive/directory uploads on versioned/unversioned buckets.

For human-readable references, use a disposable fixture and its compiled pipeline:

```bash
uv run --all-packages --all-extras --with playwright==1.55.0 python tools/reference_names_browser_smoke.py --url FIXTURE_URL --definition FIXTURE_PIPELINE --output tmp/reference-browser
```

The probe registers a catalog/experiment and executes two Runs with a unique
reuse key. It checks names and exact identity through lists, details, graph
inspectors, provenance, comparison, selectors and deletion context, plus bounded
batches, lookup failures, stale replies and narrow layouts. Pass `--token-file`
for authenticated/sign-out coverage. Captures project anonymous example text in
the browser only; inspect and discard captures before retaining neutral receipts.

For the sidebar project/status/connection context and reclaimed workspace height:

```bash
uv run --all-packages --all-extras --with playwright==1.55.0 python tools/sidebar_context_browser_smoke.py --url FIXTURE_URL --token-file TOKEN_FILE --output tmp/sidebar-context-browser
```

The read-only probe checks desktop/narrow/short layouts, long project identity,
keyboard and independent menu scrolling, readiness recovery and sign-out/connect.
Omit `--token-file` for a no-token fixture. Captures use anonymous project text
and redact runtime IDs; review/discard them before retaining neutral receipts.
The graph workspace probe also accepts `--token-file` and permits read-only name
lookups during selection while still rejecting graph/page refetches.

For filter autocomplete, use a disposable fixture populated by the general
browser journey so Runs/executions and related selectors have real records:

```bash
uv run --all-packages --all-extras --with playwright==1.55.0 python tools/filter_autocomplete_browser_smoke.py --url FIXTURE_URL --token-file TOKEN_FILE --output tmp/filter-autocomplete-browser
```

The probe adds anonymous experiments, checks recent/ID/name suggestions, exact
values and inline captions, exact omitted counts, dependent scopes/order, equal
control heights, mouse/keyboard input, delayed/failing responses, every
list/reference/type filter, sign-out and viewport bounds. Optional captures redact resource/project
identities; inspect and discard them before retaining neutral receipts.

Stop the fixture with Ctrl+C. Its data remains for inspection; choose a new
absent directory for another independent probe rather than resetting existing
history. Record the actual browser/OS and execution results. Automated headless
Chromium coverage does not imply qualification of every browser or replace
manual review of captured layouts and accessibility.

## Working on a change

Use a suitable topic branch. Read the open records under
[workflows](.macrostates/implementation/workflows/) and ensure one covers the
requested work before editing files. Follow the selected
[Process](.macrostates/specs/001_process/README.md) and
[Repository](.macrostates/specs/010_repository-1/README.md) policies for tracking,
review, integration, and release preparation.

Keep specification changes deliberate. Dockflow-owned requirements are organized
into [general Dockflow](.macrostates/specs/051_dockflow/README.md),
[CLI](.macrostates/specs/052_dockflow-cli/README.md),
[Pipelines](.macrostates/specs/053_dockflow-pipelines/README.md), and
[Artifacts](.macrostates/specs/054_dockflow-artifacts/README.md) packages. External
specification snapshots are immutable. Develop upstream package changes in their
canonical repositories and deliberately select a new released version here.

Before a specification commit, inspect exactly what is staged and run:

```bash
.venv-macrostates/bin/macrostates check --staged
git diff --cached --check
```

Workflow closure requires the definer's explicit confirmation. Close all open
workflows before submitting a reviewed integration proposal under Process;
proposal review, integration, tagging, and publication remain separate steps.

## Restoring specification snapshots

A normal checkout includes the snapshots. If an unchanged locked package copy is
missing, restore the selected releases with Git network access:

```bash
.venv-macrostates/bin/macrostates install --locked
.venv-macrostates/bin/macrostates check
```

Review composition, lock, and package changes together. Do not rewrite the lock
to accept unexplained modifications or select newer releases automatically.

Keep local credentials, environment files, private notes, caches, and generated
artifacts out of commits. Use a named subdirectory under `tmp/` for disposable
work; only `tmp/.gitkeep` is tracked.

## Preparing and publishing a release

All four distributions share root `VERSION`. Work on a release branch, update
that file, run `uv run python tools/version.py --sync`, and refresh `uv.lock`
without unrelated upgrades. Update the changelog, package documentation and
generated API reference. Complete the existing specification/implementation
baseline review and workflow closure before submitting reviewed integration;
see the [release policy](.macrostates/specs/051_dockflow/004_releases.md).

Publication uses four separate PyPI publishers. Each has owner
`dockflow-project`, repository `dockflow` and workflow filename `publish.yaml`:

| PyPI project | GitHub environment |
| --- | --- |
| `dockflow-core` | `pypi-core` |
| `dockflow-cli` | `pypi-cli` |
| `dockflow-pipelines` | `pypi-pipelines` |
| `dockflow-artifacts` | `pypi-artifacts` |

Distinct environments avoid PyPI's duplicate pending-publisher restriction.
Configure required maintainer review and allow only `main` in each GitHub
environment. Publishing uses OIDC; no PyPI API token is stored. GHCR publication
uses the repository's short-lived `GITHUB_TOKEN`. The first container package
must be made public and its anonymous pull verified before announcing it.

After reviewed integration and successful CI on that exact main commit:

1. Manually run **Build release candidate (no publication)** on `main`.
   It builds the four wheels/sdists once, verifies clean installation and
   independent sdist rebuilding, builds the service using those wheels, and
   runs a disposable Docker-in-Docker deployment check. It retains the tested
   image archive, package files, verification receipts and a hash manifest as
   `dockflow-release-RUN_ID` for 30 days.
2. Inspect the candidate, receipts and manifest SHA-256 in the run summary.
   Obtain approval for those exact bytes and the release scope. Create the
   authorized annotated application and implementation tags on the reviewed
   release commit; publish new related refs atomically. For 0.3.0 these are
   `v0.3.0`, `imp-2.0.0` and `specs-2.0.0`. For a later unchanged specification
   baseline, reuse its original tag only after verifying ancestry and byte-identical
   specification trees. All
   existing application and baseline tags remain immutable.
3. Manually run **Publish approved release** on the same main commit, supplying
   the candidate run ID and reviewed manifest SHA-256. Approve the protected
   environments for that candidate. The workflow checks provenance, annotated
   tags and every file hash, publishes Core and CLI before Artifacts, then Pipelines, loads and
   pushes the preserved service image, and creates the shared GitHub release
   with verification assets. No package or image is rebuilt during publication.
4. Verify all PyPI file hashes and public installation, the GHCR image digest
   and anonymous pull, and the release assets before announcing completion.

If publication partly succeeds, rerun **Publish approved release** with the
same successful candidate run ID and manifest hash. Existing PyPI files, image
contents and GitHub assets must match; conflicting bytes stop publication.
Do not rerun the candidate build to recover an upload. Keep the original bundle
available until the release finishes; an expired/missing candidate is a recovery
issue, not authorization to replace an already published version.

`tools/release.py` checks bundles without building or publishing. The
publication script is restricted to the canonical GitHub Actions main context.
Application and implementation tags bind the exact publication source. An
unchanged specification baseline can identify an ancestor only when its complete
`.macrostates/specs` tree equals the candidate's tree. Lightweight tags, unrelated
history, changed specification bytes and mismatched implementation tags fail.

Publication uses the official pinned `pypa/gh-action-pypi-publish` v1.14.3 action
with Trusted Publishing and PEP 740 attestations. This upstream version includes
the CA incident fix; there is no custom publishing container, wrapper, token
fallback or alternate upload path. Candidate provenance, hash and collision
checks run before the protected publishing steps.

Candidate 39787991471 must not be resumed: its image contains affected CA
bundles. The existing 0.1.0 tags and CLI files are immutable. Version 0.1.1 uses a
new coordinated candidate and needs approval for its exact manifest before
publication.

## Cache conformance

Ordinary tests include SQLite coordination, independent-process contention and
fault tests. To exercise PostgreSQL, provide a disposable database through
`DOCKFLOW_TEST_CACHE_POSTGRES_DSN` and run:

```bash
uv run --locked --all-extras pytest packages/pipelines/tests/integration/test_cache_registry.py
```

The suite uses fresh scopes and retains fencing records; drop the disposable
database/container after the run. CI supplies a pinned PostgreSQL service on
Linux for both supported Python targets. Tests include repeated barriers of 20
spawned processes and producer termination; do not replace these with thread mocks.
Real S3 tests additionally use `DOCKFLOW_TEST_CACHE_S3_ENDPOINT` and standard
AWS-compatible test credentials, creating/removing only a unique test bucket:

```bash
uv run --locked --all-extras pytest packages/pipelines/tests/integration/test_cache_s3.py
```

Use disposable local test providers and never export resolved connection strings,
credentials, host paths or raw provider logs into validation records.
