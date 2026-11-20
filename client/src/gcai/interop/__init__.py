"""Working with the documents the GC-AI service generates.

- `validate` runs the SBOL validation the service skips.
- `roundtrip` compares what was detected with what was encoded.
- `sbol_db` publishes a design to an SBOL DB registry.

`validate` and `roundtrip` need the sbol extra; `sbol_db` needs the db extra.
"""

from gcai.interop.roundtrip import EncodedPart, Mismatch, RoundTripReport, check_order, encoded_parts
from gcai.interop.sbol_db import FoundObject, PublishResult, SbolDb
from gcai.interop.validate import ValidationIssue, validate

__all__ = [
    "EncodedPart",
    "FoundObject",
    "Mismatch",
    "PublishResult",
    "RoundTripReport",
    "SbolDb",
    "ValidationIssue",
    "check_order",
    "encoded_parts",
    "validate",
]
