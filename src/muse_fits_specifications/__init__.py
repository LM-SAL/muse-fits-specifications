"""
Machine-readable MUSE FITS keyword specifications and header validation.
"""

from .spec import LEVELS, HduSpec, KeywordSpec, Spec, SpecDefinitionError, load_spec
from .validation import HeaderValidationError, ensure_valid, validate

__all__ = [
    "LEVELS",
    "HduSpec",
    "HeaderValidationError",
    "KeywordSpec",
    "Spec",
    "SpecDefinitionError",
    "ensure_valid",
    "load_spec",
    "validate",
]
