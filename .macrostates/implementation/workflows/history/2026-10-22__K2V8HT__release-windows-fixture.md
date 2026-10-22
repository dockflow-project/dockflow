# Release Windows HTTP fixture correction

- Project phase: active
- Workflow type: Release preparation
- Status: completed
- Delivery state: accepted
- Change depth: small
- Branch: release/0.1.0
- Requested by: Definer
- Implementer: Implementer
- Started at: 2026-10-22 12:54 UTC
- Last updated at: 2026-10-22 13:27 UTC
- Closed at: 2026-10-22 13:27 UTC

## Objective and origin

Complete the authorized release integration after PR CI exposed a repeatable
Windows test-fixture failure. Source origin is
5580ac2588bc0c5d248890ea701b22e96c1aef12; the current primary target remains
fc00ff0325483e62505edf694540abbc798576a6. The accepted specs-0.1.0/imp-0.1.0
declarations are candidates awaiting reviewed integration, not finalized tags.
This correction is part of the first release scope and allocates no new version.

## Evidence and correction

Branch CI run 39781526554 passed all nine jobs. PR run 39781585418 failed the
Windows/Python 3.13 cross-origin POST/308 redirect case with a connection abort;
retrying only the failed job reproduced it. Both failures occurred before the
redirect assertion could observe an HTTP response. Other PR jobs passed.

The loopback HTTP fixture responds to POST without consuming its request body.
Read the declared body before responding, so the server does not close with
unread inbound data. Preserve every same/cross-origin redirect assertion and
the real HTTP transport. No production behavior or security policy changes.

## Verification and closure criteria

All 82 base-platform tests passed, including the 22 HTTP client cases. Ruff,
formatting, composition integrity and diff checks passed. The first-release
review records this test-only correction and the original CI failures without
rewriting the closed preparation record. Actual Windows confirmation remains a
hosted check after submission; integration remains authorized only after all
hosted checks pass.

## Closure

The Definer explicitly approved closure and submission of this correction on
2026-10-22, followed by the already authorized release integration once CI
passes. All 38 workflows are closed. Actual hosted qualification and integration
outcomes remain in the proposal/CI records; no publication is claimed here.
