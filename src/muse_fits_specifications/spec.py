"""
Load the packaged MUSE FITS keyword specification.

The specification is ``specs/keywords.yml`` (:data:`KEYWORDS_PATH`), generated from the
mission keyword sheet ``specs/keywords.csv`` (:data:`SHEET_PATH`) by
:mod:`muse_fits_specifications.sheet`, which documents the sheet's rules. Each keyword
lists the levels whose files carry it: every file of the level (``all``), or only the CI
or SG camera files. A keyword is never optional. Each level's
``specs/<level>/_meta.toml`` carries what the sheet lacks: spec name, version, title,
source document and HDU layout.

A level whose CI and SG files differ, in keywords or HDUs, is loaded per camera type:
``load_spec("level1", "SG")``.

Cards the FITS library writes and consumes itself (table structure, tile-compression
bookkeeping, checksums) are flagged ``library_owned``: astropy hides or rewrites them in
``hdul[1].header``, so the validator and :func:`example_header` leave them to the
library.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from types import MappingProxyType
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

LEVELS = ("level0", "level1", "level2", "level3")
FAMILIES = ("CI", "SG")
"""
The camera types, as the sheet's level columns name them.
"""

SHEET = "keywords.csv"
SHEET_PATH = files("muse_fits_specifications") / "specs" / SHEET
"""
The packaged keyword sheet, e.g. ``SHEET_PATH.read_text(encoding="utf-8-sig")`` for the
raw CSV.
"""

KEYWORDS = "keywords.yml"
KEYWORDS_PATH = files("muse_fits_specifications") / "specs" / KEYWORDS
"""
The packaged YAML generated from the sheet, which the loader reads.
"""

_META_FIELDS = ("spec", "spec_version", "title", "source_document")


class SpecDefinitionError(Exception):
    """
    The keyword sheet, its YAML or a level's ``_meta.toml`` violates the spec rules.
    """


@dataclass(frozen=True)
class KeywordSpec:
    name: str
    type: str | None = None
    minimum: int | float | None = None
    maximum: int | float | None = None
    comment: str = ""
    notes: str = ""
    library_owned: bool = False
    values: tuple[bool | int | float | str, ...] | None = None
    format: str | None = None
    section: str = ""
    mnemonic: str = ""


@dataclass(frozen=True)
class HduSpec:
    name: str
    kind: str
    compression: str | None = None
    family: str | None = None


@dataclass(frozen=True)
class Spec:
    name: str
    version: str
    title: str
    source_document: str
    hdus: tuple[HduSpec, ...]
    keywords: Mapping[str, KeywordSpec]
    unassigned: tuple[KeywordSpec, ...] = ()
    family: str | None = None

    @property
    def sections(self) -> tuple[str, ...]:
        """
        The sheet sections of this level's keywords, in sheet order.
        """
        return tuple(dict.fromkeys(kw.section for kw in self.keywords.values()))


@cache
def load_sheet() -> tuple[tuple[Mapping[str, str], KeywordSpec], ...]:
    """
    Every sheet row, as ``(levels, keyword)`` pairs in sheet order.

    ``levels`` maps each level whose files carry the keyword to ``"all"``, ``"CI"`` or
    ``"SG"``; it is empty for a row parked in no level.
    """
    rows = []
    for section in yaml.safe_load(KEYWORDS_PATH.read_text(encoding="utf-8")):
        for entry in section["keywords"]:
            levels = MappingProxyType(entry.pop("levels"))
            if "values" in entry:
                entry["values"] = tuple(entry["values"])
            rows.append((levels, KeywordSpec(**entry, section=section["section"])))
    return tuple(rows)


def _collect(
    rows: Iterable[tuple[Mapping[str, str], KeywordSpec]], level: str, family: str | None = None
) -> tuple[dict[str, KeywordSpec], tuple[KeywordSpec, ...]]:
    """
    Split the rows that ``level`` (and ``family``) carries into keywords and unassigned
    fields.
    """
    keywords: dict[str, KeywordSpec] = {}
    unassigned: list[KeywordSpec] = []
    for levels, kw in rows:
        marker = levels.get(level)
        if family is None and marker in FAMILIES:
            msg = (
                f"{KEYWORDS}: {kw.name or 'an unassigned ISP field'} is {marker}-only in {level}, "
                f"but specs/{level}/_meta.toml does not set per_camera = true"
            )
            raise SpecDefinitionError(msg)
        if marker is None or marker not in ("all", family):
            continue
        if not kw.name:
            unassigned.append(kw)
        elif kw.name in keywords:
            msg = f"{KEYWORDS}: {kw.name} is listed twice for {level}"
            raise SpecDefinitionError(msg)
        else:
            keywords[kw.name] = kw
    if not keywords:
        msg = f"{KEYWORDS}: no keywords marked for {level}"
        raise SpecDefinitionError(msg)
    return keywords, tuple(unassigned)


def _meta_path(level: str):
    return files("muse_fits_specifications") / "specs" / level / "_meta.toml"


def defined_levels() -> tuple[str, ...]:
    """
    The levels that have a ``specs/<level>/_meta.toml``, in ``LEVELS`` order.
    """
    return tuple(level for level in LEVELS if _meta_path(level).is_file())


def _parse_meta(text: str, source: str) -> dict:
    """
    Parse a level's ``_meta.toml``; ``source`` names the file in errors.
    """
    try:
        meta = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        msg = f"{source}: invalid TOML: {exc}"
        raise SpecDefinitionError(msg) from exc
    for field in _META_FIELDS:
        if not isinstance(meta.get(field), str):
            msg = f"{source}: {field} must be a quoted string"
            raise SpecDefinitionError(msg)
    if not isinstance(meta.get("per_camera", False), bool):
        msg = f"{source}: per_camera must be true or false"
        raise SpecDefinitionError(msg)
    hdus = meta.get("hdus")
    if not isinstance(hdus, list) or not hdus:
        msg = f"{source}: needs at least one [[hdus]] table"
        raise SpecDefinitionError(msg)
    for hdu in hdus:
        if not (
            isinstance(hdu, dict)
            and isinstance(hdu.get("name"), str)
            and isinstance(hdu.get("kind"), str)
            and isinstance(hdu.get("compression", ""), str)
            and hdu.get("family", FAMILIES[0]) in FAMILIES
        ):
            msg = (
                f"{source}: each [[hdus]] table needs string name and kind, optionally compression "
                f"and family ({' or '.join(FAMILIES)}); got {hdu!r}"
            )
            raise SpecDefinitionError(msg)
        if "family" in hdu and not meta.get("per_camera", False):
            msg = f"{source}: an HDU with a family needs per_camera = true; got {hdu!r}"
            raise SpecDefinitionError(msg)
    return meta


@cache
def _meta(level: str) -> dict:
    source = f"specs/{level}/_meta.toml"
    if level not in defined_levels():
        msg = f"{source} does not exist; add it to define {level}"
        raise SpecDefinitionError(msg)
    return _parse_meta(_meta_path(level).read_text(encoding="utf-8"), source)


def families(level: str) -> tuple[str | None, ...]:
    """
    :data:`FAMILIES` if ``level``'s CI and SG files differ, else ``(None,)``.

    The level's ``_meta.toml`` decides it with ``per_camera = true``, so a sheet export
    cannot change which levels need a camera type; a CI- or SG-only row in any other
    level fails to load. Pass each to :func:`load_spec` to cover every kind of file of
    the level.
    """
    per_camera = level in defined_levels() and _meta(level).get("per_camera", False)
    return FAMILIES if per_camera else (None,)


@cache
def load_spec(level: str, family: str | None = None) -> Spec:
    """
    Load one level's specification, e.g. ``load_spec("level0")``.

    A level whose CI and SG files differ (see :func:`families`) needs ``family``,
    ``"CI"`` or ``"SG"``, e.g. ``load_spec("level1", "SG")``; other levels ignore it.
    """
    if level not in LEVELS:
        msg = f"unknown level {level!r}; expected one of {LEVELS}"
        raise ValueError(msg)
    if family not in (None, *FAMILIES):
        msg = f"unknown camera family {family!r}; expected one of {FAMILIES}"
        raise ValueError(msg)
    meta = _meta(level)
    if families(level) == (None,):
        family = None
    elif family is None:
        msg = f"{level} differs between CI and SG files; pass family='CI' or family='SG'"
        raise ValueError(msg)
    keywords, unassigned = _collect(load_sheet(), level, family)
    return Spec(
        name=meta["spec"],
        version=meta["spec_version"],
        title=meta["title"],
        source_document=meta["source_document"],
        hdus=tuple(
            HduSpec(hdu["name"], hdu["kind"], hdu.get("compression"), hdu.get("family"))
            for hdu in meta["hdus"]
            if hdu.get("family") in (None, family)
        ),
        keywords=MappingProxyType(keywords),
        unassigned=unassigned,
        family=family,
    )


_PLACEHOLDERS = {"bool": False, "int": 0, "float": 0.0, "str": "UNKNOWN", None: 0}


def example_header(spec: Spec) -> dict[str, bool | int | float | str]:
    """
    A conforming header: one value for every keyword the mission writes.

    Generators (simulators, fixture writers) start from this so their files conform to
    the same spec the validator enforces. Values are the first allowed value, else the
    lower limit, else a neutral typed placeholder (``0``/``0.0``/``UNKNOWN``; presence-
    only keywords get ``0``). Library-owned cards are left to the FITS library. The
    result passes :func:`~muse_fits_specifications.validation.validate`.
    """
    return {
        name: kw.values[0] if kw.values else kw.minimum if kw.minimum is not None else _PLACEHOLDERS[kw.type]
        for name, kw in spec.keywords.items()
        if not kw.library_owned
    }
