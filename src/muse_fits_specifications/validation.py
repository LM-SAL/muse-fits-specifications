"""
Validate FITS headers against a loaded MUSE specification.

Keywords not in the spec are ignored: FITS headers legitimately carry history and other
cards the mission spec does not govern. Library-owned cards
(``KeywordSpec.library_owned``) are skipped too: astropy hides or rewrites them in
``hdul[1].header``. Astropy consumes the compression cards through the decompressor;
checking existing checksum cards requires ``fits.open(..., checksum=True)`` and is
separate from this header validator.
"""

from __future__ import annotations

from math import isfinite
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .spec import KeywordSpec, Spec


class HeaderValidationError(Exception):
    def __init__(self, spec_name: str, errors: list[str]):
        self.errors = errors
        super().__init__(f"header violates {spec_name}: " + "; ".join(errors))


def _check_type(kw: KeywordSpec, value: object) -> str | None:
    if kw.type == "bool" and not isinstance(value, bool):
        return f"{kw.name} must be a boolean, got {value!r}"
    if kw.type == "int" and (isinstance(value, bool) or not isinstance(value, int)):
        return f"{kw.name} must be an integer, got {value!r}"
    if kw.type == "float":
        # FITS writers may emit a float-valued card without a decimal point,
        # which reads back as int; accept it.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return f"{kw.name} must be numeric, got {value!r}"
        if not isfinite(float(value)):
            return f"{kw.name} must be finite, got {value!r}"
    if kw.type == "str" and not isinstance(value, str):
        return f"{kw.name} must be a string, got {value!r}"
    return None


def _check_value(kw: KeywordSpec, value: object) -> str | None:
    problem = _check_type(kw, value)
    if problem is not None:
        return problem
    # Limits only exist on numeric keywords (the loader enforces it), so the
    # type check above guarantees a comparable value here.
    if kw.minimum is not None and value < kw.minimum:  # type: ignore[operator]
        return f"{kw.name} must be >= {kw.minimum}, got {value!r}"
    if kw.maximum is not None and value > kw.maximum:  # type: ignore[operator]
        return f"{kw.name} must be <= {kw.maximum}, got {value!r}"
    return None


def validate(header: Mapping[str, Any], spec: Spec) -> list[str]:
    """
    Return every way ``header`` violates ``spec``; empty means valid.

    Every keyword of the level must be present with the sheet's type and within its
    limits, except library-owned cards. Checksum verification is handled separately by
    the FITS library when explicitly enabled.
    """
    errors = []
    for name, kw in spec.keywords.items():
        if kw.library_owned:
            continue
        if name not in header:
            errors.append(f"missing keyword {name}")
            continue
        problem = _check_value(kw, header[name])
        if problem is not None:
            errors.append(problem)
    return errors


def ensure_valid(header: Mapping[str, Any], spec: Spec) -> None:
    """
    Raise :class:`HeaderValidationError` if ``header`` violates ``spec``.
    """
    errors = validate(header, spec)
    if errors:
        raise HeaderValidationError(spec.name, errors)
