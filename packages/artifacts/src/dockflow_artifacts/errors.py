"""Public exceptions; storage clients must not expose configuration secrets."""


class ArtifactError(ValueError):
    """Invalid input, unsupported storage or a failed storage operation."""


class ConflictError(ArtifactError):
    """The destination is reserved for another immutable publication."""


class IntegrityError(ArtifactError):
    """Source or published contents do not match their recorded inventory."""
