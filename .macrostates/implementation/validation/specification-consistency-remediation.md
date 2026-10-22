# Specification consistency remediation

Validated at 2026-10-21 15:57 (UTC), against the uncommitted development tree.
Application version remains `0.1.0.dev0`; provisional project baselines and
acceptance state are unchanged. No publication or merge was performed.

## Contract and requirement preservation

| Change | Owning location and retained requirements |
| --- | --- |
| External publication | Pipelines 006 owns URI-parameter/importer behavior; 004 admits that standard IR. Managed layout, immutable publication, external ownership, source admission and lineage stay intact. Artifacts 004 specializes the integration and declares the Pipelines specification dependency. |
| Network boundary | Artifacts 003 keeps construction local. Lazy S3 initialization preserves error redaction, missing-extra diagnostics and existing publication/verification semantics. |
| Configuration provenance | Pipelines 003 defines origins and historical behavior; 010 and OpenAPI expose the Run snapshot through existing routes/CLI. No command, authentication exception or migration was added. |
| Compatibility | Shared policy distinguishes tested versions from install bounds. Artifacts metadata/lock no longer forbid a newer Python without evidence. Newer interpreters are not newly qualified by this change. |
| Anonymous authoring | Root AGENTS preserves the explicit owner instruction over conflicting Process defaults. Shared 006 defines documentation placement/maintenance. Imported versions, bytes and notices are preserved. |
| Release checklist | Shared 004 names CLI, Pipelines and Artifacts wheel/sdist publication and image accounting; candidate approval and exact-byte rules remain intact. |
| Review defaults | Pipelines 012's repeated default table now links to 001–011/013 topic owners. The original MLMD/platform/source-build constraints remain in 012; SDK/IR candidates remain in 004 and shared Python targets remain in 051/002. |
| Qualification checklist | Pipelines 012 maps review areas to A01–A31 and managed/external publication coverage in 011. No existing acceptance scenario or native-platform obligation was removed. |
| Status/version prose | Package metadata/composition own exact versions; current implementation records own completion status. CLI and package-count prose no longer deny present implementation. |

The stable document paths and A01–A31 identifiers are preserved. The upstream
Process handoff remains an optional canonical follow-up; local anonymous-authoring
behavior is already explicit and durable.

## Package-version impact

- General Dockflow `0.4.0`: additive documentation/maintenance policy and clarified
  shared release completeness.
- CLI `0.2.1`: editorial status correction only.
- Pipelines `4.1.0`: additive configuration origins and external-publication
  clarification/acceptance, plus requirement-preserving guide consolidation.
- Artifacts `2.1.0`: explicit integration dependency and constructor/qualification
  clarifications, preserving public Python API and publication formats.

Package metadata, root composition and entrypoint agree. No application version,
project baseline or imported package version was allocated by these changes.

## Verification

- Regression suite on Python 3.13.16: **491 passed, 16 deselected** with
  `pytest -q -m 'not docker and not s3'`. Local HTTP tests required execution
  outside the filesystem/network sandbox. No Docker or live S3 test was claimed.
- Regression coverage includes deferred S3 client construction through direct
  and file configuration, optional dependency isolation, setting precedence and
  origins, immutable historical API/CLI inspection, legacy snapshots, and
  compilation/admission of the publisher example's standard typed-importer graph.
- Macrostates composition/dependency/import-integrity checks passed.
- Application version and offline lock consistency checks passed.
- Ruff lint and changed-Python formatting checks passed. Pyright: no errors or
  warnings. Generated OpenAPI/Markdown reference is current.
- Specification/document links: 75 Markdown files, 224 relative links and 34
  heading fragments checked; no missing targets or fragments.
- All three wheels/sdists built offline. Clean CLI-only, Artifacts-only and
  combined-base installation, optional-dependency isolation, and independent
  source-distribution rebuilding passed.
- Dependency deprecation/advisory warnings were reported by the test framework
  and KFP client; they did not fail tests. No dependency was added to silence them.
- No native KFP, Docker, live object-store, newer-Python or additional platform
  qualification was rerun. Existing qualification limits remain explicit.

## Deliverable state

Delivered for review, awaiting explicit acceptance/closure. The assessment report
under `tmp/reviews/` records the disposition of S01–S08. Runtime code, tests,
public references and local specifications agree for the corrected surfaces.
