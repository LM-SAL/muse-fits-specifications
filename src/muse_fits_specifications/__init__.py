"""
Machine-readable MUSE FITS keyword specifications and header validation.
"""

from .spec import (
    FAMILIES,
    KEYWORDS_PATH,
    LEVELS,
    SHEET_PATH,
    HduSpec,
    KeywordSpec,
    Spec,
    SpecDefinitionError,
    example_header,
    families,
    load_spec,
)
from .validation import HeaderValidationError, ensure_valid, validate

__all__ = [
    "FAMILIES",
    "KEYWORDS_PATH",
    "LEVELS",
    "SHEET_PATH",
    "HduSpec",
    "HeaderValidationError",
    "KeywordSpec",
    "Spec",
    "SpecDefinitionError",
    "ensure_valid",
    "example_header",
    "families",
    "load_spec",
    "validate",
]
