"""Validating a generated document.

The service reports whether it could write a document, not whether that
document is valid: its own validation result is discarded before it is checked.
This runs the check the service skips.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from gcai.interop._doc import load


@dataclass(frozen=True)
class ValidationIssue:
    """One problem reported by the SBOL validator."""

    severity: Literal["error", "warning"]
    object_id: str
    rule_id: str | None
    message: str

    def __str__(self) -> str:
        where = f" [{self.object_id}]" if self.object_id else ""
        rule = f" ({self.rule_id})" if self.rule_id else ""
        return f"[{self.severity}]{where}{rule} {self.message}"


def validate(document: bytes | str) -> list[ValidationIssue]:
    """Every problem with `document`, errors first.

    A document holding nothing is reported rather than passed: anything that
    parses as RDF and declares no SBOL objects, a file of the wrong kind
    included, has no problems to find and would otherwise look valid.
    """
    doc = load(document)
    report = doc.validate()
    issues = [_issue("error", item) for item in report.errors]
    issues += [_issue("warning", item) for item in report.warnings]
    if not list(doc.objects):
        issues.append(
            ValidationIssue(
                severity="warning",
                object_id="",
                rule_id=None,
                message="this document declares no SBOL objects; check that it is the file you meant",
            )
        )
    return issues


def _issue(severity: Literal["error", "warning"], item: object) -> ValidationIssue:
    return ValidationIssue(
        severity=severity,
        object_id=str(getattr(item, "object_id", "") or ""),
        rule_id=(str(getattr(item, "rule_id", "")) or None),
        message=str(getattr(item, "message", item)),
    )
