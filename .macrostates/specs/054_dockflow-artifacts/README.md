# Dockflow Artifacts contract

This package defines the Dockflow Artifacts contract, independently versioned
from application builds and project baselines. The optional Dockflow integration
consumes the declared Pipelines
specification dependency; the Python library has no runtime CLI/Pipelines
dependency. Implementation status, qualification and publication belong to the
[implementation records](../../implementation/main.md).

## Core reading order

1. [Product and boundaries](001_product.md)
2. [Publication and integrity](002_publication.md)
3. [Configuration and storage](003_storage.md)
4. [KFP integration](004_kfp.md)
5. [Packaging and acceptance](005_acceptance.md)

The initial scope is reusable publishing code and optional KFP helpers.
Future artifact functionality belongs in this generic project when explicitly
specified; neither a server nor a general workflow engine is implied.
