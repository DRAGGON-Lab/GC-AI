"""Errors the client raises."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from gcai.validation import Issue


class GCAIError(Exception):
    """Base class for every error this package raises."""


class GCAIConnectionError(GCAIError):
    """The service could not be reached."""


class GCAIResponseError(GCAIError):
    """The service answered, and the answer was a failure.

    Branch on `status_code`; `message` is written for a human reader and is not
    a stable identifier.
    """

    def __init__(
        self,
        status_code: int,
        message: str,
        body: str = "",
        *,
        code: str | None = None,
        issues: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(f"GC-AI returned {status_code}: {message}")
        self.status_code = status_code
        self.message = message
        self.body = body
        self.code = code
        self.issues = issues or []


class DesignValidationError(GCAIError):
    """A design was rejected before it was sent."""

    def __init__(self, issues: "list[Issue]") -> None:
        detail = "\n".join(f"  {issue.path}: {issue.message}" for issue in issues)
        super().__init__(f"the design is not valid:\n{detail}")
        self.issues = issues
