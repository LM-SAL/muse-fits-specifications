"""
Validate FITS headers against a loaded MUSE specification.

Keywords not in the spec are ignored: FITS headers legitimately carry structural and
history cards the mission spec does not govern.
"""

from __future__ import annotations

from datetime import datetime
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
    if kw.values is not None and value not in kw.values:
        return f"{kw.name} must be one of {list(kw.values)}, got {value!r}"
    if kw.format == "isot":
        try:
            datetime.fromisoformat(str(value).strip())
        except ValueError:
            return f"{kw.name} must be an ISO 8601 timestamp, got {value!r}"
    return None


def validate(
    header: Mapping[str, Any],
    spec: Spec,
    *,
    skip_sections: tuple[str, ...] = (),
) -> list[str]:
    """
    Return every way ``header`` violates ``spec``; empty means valid.

    ``skip_sections`` excludes whole sections, e.g. the structural ``fits``
    section whose cards (checksums, tile-compression bookkeeping) are owned
    and verified by the FITS library rather than header comparison.
    """
    errors = []
    for name, kw in spec.keywords.items():
        if kw.section in skip_sections:
            continue
        if name not in header:
            if kw.required:
                errors.append(f"missing required keyword {name}")
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
