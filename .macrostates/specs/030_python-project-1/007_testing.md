# Testing

Python projects should use `pytest` for unit and integration testing.

Testing should protect externally observable behavior, compatibility surfaces,
and important internal contracts without making private implementation details
unnecessarily hard to change.

## Test levels

Use these test levels inside this package:

- Unit tests: verify small units of behavior without real network access,
  external providers, persistent services, or uncontrolled filesystem effects.
- Integration tests: verify interactions between project components or between
  the project and controlled local test dependencies.
- API contract tests: verify that APIs keep their documented request, response,
  status, error, and compatibility behavior.

End-to-end tests, browser tests, load tests, and other high-level specialized
testing are outside this package. Other packages or project-specific
specifications may define those tools and expectations.

## Test directories

Tests should live under `./tests/` and be grouped by level:

```text
tests/
  unit/
  integration/
  contract/
```

Place unit tests under `./tests/unit/`, integration tests under
`./tests/integration/`, and API contract tests under `./tests/contract/`.

## Pytest

Configure `pytest` through project tooling configuration, preferably in
`pyproject.toml`.

Register standard markers for test levels:

- `unit`
- `integration`
- `contract`

Markers should match the test directory when practical, so tests can be selected
by directory or marker.

Tests should be runnable from a clean checkout after installing documented
development dependencies.

Tests should be deterministic by default. Avoid tests that depend on wall-clock
timing, test order, real external services, local machine state, or persistent
data left by previous runs.

Use fixtures for reusable setup. Keep fixtures explicit enough that a reader can
understand what state each test receives.

Fixtures should default to function scope. Use broader fixture scopes only when
the shared state is intentional, safe, and does not create order-dependent
tests.

Test files should use pytest-discoverable names such as `test_*.py`. Test
functions and methods should use `test_*` names.

## Unit tests

Unit tests should be fast, focused, and isolated.

Use unit tests for:

- Pure domain behavior.
- Validation and parsing rules.
- Error handling branches.
- Boundary translation that can be exercised without real external services.
- Compatibility behavior that does not require integration setup.

Unit tests should not contact real providers. They should use fakes, stubs,
fixtures, or in-memory implementations when a dependency is needed.

When fixing a bug, add or update a unit test that would have failed before the
fix when that is practical. If a regression test is not practical, explain why.

## Integration tests

Integration tests should verify meaningful collaboration between components.

Use integration tests for:

- Persistence or filesystem behavior using controlled temporary locations.
- Adapter behavior against local fakes or recorded safe fixtures.
- CLI or service boundaries when they can be exercised without external
  provider access.
- Configuration wiring that is difficult to prove with unit tests alone.

Integration tests must not contact real providers by default. If a project needs
provider-backed tests, those tests must be explicitly opt-in, marked, skipped by
default, and documented by a project-specific specification.

## API contract tests

APIs should have contract tests.

Contract tests should verify the externally observable API contract, including:

- Supported endpoints, operations, or messages.
- Request validation.
- Response status or result classification.
- Response body shape and required fields.
- Error format and error semantics.
- Backward-compatible behavior for documented clients.

Contract tests should focus on the public contract rather than private
implementation structure. When an API contract is defined by a schema or
specification file, contract tests should use that authoritative source when
practical.

When an API schema, OpenAPI document, protocol definition, or other contract
source exists, avoid duplicating the contract manually in tests unless the
duplication protects an important compatibility surface.

When an API changes deliberately, update the contract source and contract tests
together.

## Test data

Test data should be small, safe, and committed only when it is stable and useful
for repeatable tests.

Never commit secrets, credentials, access tokens, private keys, or real account
data as test fixtures.

Large, generated, temporary, or local-only test data should follow the
repository package rules for generated and temporary files.

## Coverage posture

Use `pytest-cov` when measuring test coverage for Python code.

Coverage reports should help the Implementer find untested required behavior,
edge cases, failure paths, and compatibility surfaces. They should not be used
as a substitute for understanding whether the important behavior is actually
tested.

Do not rely on a fixed coverage percentage as the main quality signal unless a
project-specific specification requires it.

If a project-specific specification defines a coverage threshold, the threshold
should be treated as a minimum guardrail rather than proof that the test suite is
sufficient.

Untested behavior that is required by specifications should be treated as a gap
unless the implementer explains why testing it is not practical at that time.

Coverage configuration should exclude code that is not meaningful to measure,
such as generated files, test files, temporary files, or narrowly documented
integration entrypoints that cannot be exercised in normal test runs.

When coverage is collected, it should normally be collected through pytest so
the reported coverage corresponds to the same tests the project expects
Implementers to run.

## Completion expectations

When changing Python behavior, the implementer should run the relevant pytest
tests when practical.

If tests cannot be run, or if a relevant test level is intentionally skipped,
the implementer should say what was not checked and why.
