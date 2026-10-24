# Dockflow 0.2.0 release qualification

Roles: Definer and Implementer. Preparation is in progress on the release branch
from reviewed PR #4. This coordinated pre-1.0 application minor release publishes
the fresh-state contract implemented by all four packages. Its Macrostates
baseline proposal is specs-1.0.0 / imp-1.0.0, calculated from collected Major
impact, independently of the application version.

The feature source passed 790 tests on each supported interpreter with real
PostgreSQL/S3/Docker, 14 intentional skips, package/image and static checks.
Hosted PR #4 passed all 18 checks, including base Linux/macOS/Windows clients and
Linux runtime on Python 3.12/3.13. Physical multi-host, further execution platforms
and a particular serverless provider remain unqualified. No migration is provided.

This preparation changes identity, generated reference and release documentation;
runtime implementation remains unchanged. Exact merged-source CI, immutable
candidate construction and publication verification remain external release gates.
