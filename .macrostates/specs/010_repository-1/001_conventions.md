# Repository conventions

- The repository must be self-contained and buildable from a clean checkout.
- Keep configuration outside source code and commit safe defaults only.
- Never commit secrets, credentials, access tokens, private keys, or real account data.
- Prefer small modules with explicit responsibilities over framework-driven coupling.
- Keep generated data, caches, virtual environments, and local configuration out of version control.
- Do not create garbage, scratch, dataset, or temporary test files in the repository root.
- Changes should include relevant tests for observable behavior and compatibility surfaces.
- User-facing commands and persisted formats are compatibility surfaces; change them deliberately.
