# Dockflow 0.2.0 release qualification

Roles: Definer and Implementer. Preparation includes the accepted Core boundary
and all pending execution/cache features after reviewed PR #4. All four packages
share application 0.2.0; collected Major contract impact proposes specs-1.0.0 and
imp-1.0.0, independently of that application version. The prior database-package
candidate was superseded, with all original record bytes retained.

The [final Core receipt](generic-core.md) qualifies 813 tests on each of Python
3.12.15 and 3.13.17 with real PostgreSQL 18.6, S3 and Docker, 14 intentional skips
and five upstream warnings. Clean base wheel installs, standalone source rebuilds,
non-root service execution/reuse/restart, static checks and composition/integrity
pass. No third-party locked dependency changed. Exact submitted/merged source CI
and the immutable hosted candidate are still required external release gates.

Core owns generic primitives; consumers own schemas, versions, queries and
persistence logic. The same SQLite/PostgreSQL database retains execution and
artifact state. Use fresh state and SQL backup format dockflow-sql-v5; no migration
or retired-package import facade is supplied. Physical multi-host, further native
execution platforms and a particular serverless provider remain unqualified.

The Definer accepts the implementation, closes its workflows and explicitly
authorizes reviewed integration and publication. Preparation preserves exact
source/target and change records, and closes local workflows before submission.
Publication outcomes are verified externally against the preserved manifest and
annotated tags; preparation or a merge alone does not establish upload success.
