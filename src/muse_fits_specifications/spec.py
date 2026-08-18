"""
Load the packaged MUSE FITS keyword specifications.

Each level's specification is a directory of small per-section YAML files
under ``specs/<level>/`` (DKIST-style layout): ``_meta.yml`` carries the
spec-wide fields, and every other file holds one section's keywords. The
loader checks the spec files themselves against the field rules below, so a
typo in a spec fails at load time, not silently during header validation.

Keyword fields:

- ``required``: the keyword must be present in a conforming header. Structural
  cards owned by the FITS library (tile-compression bookkeeping, checksums)
  and keywords with unresolved ICD questions are recorded but not required.
- ``type``: one of bool/int/float/str; omitted when the source document does
  not yet pin the type down. Omitted means no type check.
- ``values``: closed set of allowed values.
- ``format``: ``isot`` marks an ISO 8601 timestamp string.
- ``source``: the ISP mnemonic or other upstream source of the value.
- ``example``: an example value, verbatim from the source document.

The section name is not stored per keyword; it comes from the file the
keyword lives in.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from collections.abc import Mapping

LEVELS = ("level0", "level1")

_KEYWORD_FIELDS = {
    "required": bool,
    "type": str,
    "values": list,
    "format": str,
    "source": str,
    "example": str,
    "comment": str,
}
_TYPES = ("bool", "int", "float", "str")
_FORMATS = ("isot",)


class SpecDefinitionError(Exception):
    """
    A packaged spec file violates the spec-file rules.
    """


@dataclass(frozen=True)
class KeywordSpec:
    name: str
    required: bool
    type: str | None = None
    values: tuple[Any, ...] | None = None
    format: str | None = None
    source: str | None = None
    example: str | None = None
    comment: str = ""
    section: str = ""


@dataclass(frozen=True)
class HduSpec:
    name: str
    kind: str
    compression: str | None = None


@dataclass(frozen=True)
class Spec:
    name: str
    version: int
    title: str
    source_document: str
    hdus: tuple[HduSpec, ...]
    keywords: Mapping[str, KeywordSpec]

    @property
    def sections(self) -> tuple[str, ...]:
        seen: dict[str, None] = {}
        for kw in self.keywords.values():
            seen.setdefault(kw.section)
        return tuple(seen)


def _keyword(name: str, raw: object, source: str, section: str) -> KeywordSpec:
    if not isinstance(raw, dict):
        msg = f"{source}: {name} must be a mapping"
        raise SpecDefinitionError(msg)
    unknown = set(raw) - set(_KEYWORD_FIELDS)
    if unknown:
        msg = f"{source}: {name} has unknown fields {sorted(unknown)}"
        raise SpecDefinitionError(msg)
    for fname, ftype in _KEYWORD_FIELDS.items():
        if fname in raw and not isinstance(raw[fname], ftype):
            msg = f"{source}: {name}.{fname} must be {ftype}"
            raise SpecDefinitionError(msg)
    if not isinstance(raw.get("required"), bool):
        msg = f"{source}: {name}.required is mandatory"
        raise SpecDefinitionError(msg)
    if "type" in raw and raw["type"] not in _TYPES:
        msg = f"{source}: {name}.type must be one of {_TYPES}"
        raise SpecDefinitionError(msg)
    if "format" in raw and raw["format"] not in _FORMATS:
        msg = f"{source}: {name}.format must be one of {_FORMATS}"
        raise SpecDefinitionError(msg)
    return KeywordSpec(
        name=name,
        required=raw["required"],
        type=raw.get("type"),
        values=tuple(raw["values"]) if "values" in raw else None,
        format=raw.get("format"),
        source=raw.get("source"),
        example=raw.get("example"),
        comment=raw.get("comment", ""),
        section=section,
    )


@cache
def load_spec(level: str) -> Spec:
    """
    Load one level's specification, e.g. ``load_spec("level0")``.
    """
    if level not in LEVELS:
        msg = f"unknown level {level!r}; expected one of {LEVELS}"
        raise ValueError(msg)
    root = files("muse_fits_specifications").joinpath(f"specs/{level}")
    meta_source = f"specs/{level}/_meta.yml"
    meta = yaml.safe_load(root.joinpath("_meta.yml").read_text())
    for field in ("spec", "spec_version", "title", "source_document", "hdus"):
        if field not in meta:
            msg = f"{meta_source}: missing field {field!r}"
            raise SpecDefinitionError(msg)
    hdus = tuple(HduSpec(name=h["name"], kind=h["kind"], compression=h.get("compression")) for h in meta["hdus"])
    keywords: dict[str, KeywordSpec] = {}
    for entry in sorted(root.iterdir(), key=lambda item: item.name):
        if entry.name == "_meta.yml" or not entry.name.endswith(".yml"):
            continue
        source = f"specs/{level}/{entry.name}"
        doc = yaml.safe_load(entry.read_text())
        section = doc.get("section")
        if not section or "keywords" not in doc:
            msg = f"{source}: needs 'section' and 'keywords'"
            raise SpecDefinitionError(msg)
        for name, body in doc["keywords"].items():
            if name in keywords:
                msg = f"{source}: {name} already defined in section {keywords[name].section!r}"
                raise SpecDefinitionError(msg)
            keywords[name] = _keyword(name, body, source, section)
    if not keywords:
        msg = f"specs/{level}/ has no section files"
        raise SpecDefinitionError(msg)
    return Spec(
        name=meta["spec"],
        version=int(meta["spec_version"]),
        title=meta["title"],
        source_document=meta["source_document"],
        hdus=hdus,
        keywords=MappingProxyType(keywords),
    )
