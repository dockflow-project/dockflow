"""Errors shared by the core and interface adapters."""

import uuid


class DockflowError(Exception):
    def __init__(
        self,
        message: str,
        code: str = "INVALID_ARGUMENT",
        status: int = 400,
        details: list[dict] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.details = details or []
        self.request_id = str(uuid.uuid4())

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "request_id": self.request_id,
        }
