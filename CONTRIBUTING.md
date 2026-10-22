# Contributing

Dockflow is bootstrapping its first implementation. Start with the
[specification entrypoint](.macrostates/specs/main.md) and the
[current implementation status](.macrostates/implementation/main.md).

For usage questions, first try the [documentation](docs/README.md) and
[self-contained quickstart](docs/quickstart.md). When reporting a defect, include
versions, a minimal compiled definition or reproduction, expected/actual behavior
and relevant redacted logs. Keep credentials and private datasets out of reports.
Security concerns follow [SECURITY.md](SECURITY.md).

## Local setup and checks

Use Python 3.12 or newer for the separate specification-tool bootstrap below.
Application development uses a Python 3.13 default with 3.12 compatibility
under the [shared compatibility and review policy](.macrostates/specs/051_dockflow/002_compatibility.md).

```bash
python3 -m venv .venv-macrostates
.venv-macrostates/bin/python -m pip install -r tools/macrostates/requirements.txt
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
three distributions, checks standalone Artifacts imports without optional
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

All three distributions share root `VERSION`. Work on a release branch, update
that file, run `uv run python tools/version.py --sync`, and refresh `uv.lock`
without unrelated upgrades. Update the changelog, package documentation and
generated API reference. Complete the existing specification/implementation
baseline review and workflow closure before submitting reviewed integration;
see the [release policy](.macrostates/specs/051_dockflow/004_releases.md).

The initial publication uses three pending PyPI publishers. Each has owner
`dockflow-project`, repository `dockflow` and workflow filename `publish.yaml`:

| PyPI project | GitHub environment |
| --- | --- |
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
   It builds the three wheels/sdists once, verifies clean installation and
   independent sdist rebuilding, builds the service using those wheels, and
   runs a disposable Docker-in-Docker deployment check. It retains the tested
   image archive, package files, verification receipts and a hash manifest as
   `dockflow-release-RUN_ID` for 30 days.
2. Inspect the candidate, receipts and manifest SHA-256 in the run summary.
   Obtain approval for those exact bytes and the release scope. Create the
   authorized annotated `v0.1.0`, `specs-0.1.0` and `imp-0.1.0` tags on the
   reviewed initial-release commit; publish related refs atomically. These
   initial tags are immutable. Subsequent releases require their own reviewed
   baseline/source binding rather than moving these tags.
3. Manually run **Publish approved release** on the same main commit, supplying
   the candidate run ID and reviewed manifest SHA-256. Approve the protected
   environments for that candidate. The workflow checks provenance, annotated
   tags and every file hash, publishes CLI before the other packages, loads and
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
The initial tooling requires all three annotated tags to identify the same
source commit; a later release reusing older baselines must deliberately extend
that check under the existing provenance policy.
