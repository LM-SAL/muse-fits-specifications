"""
Load the packaged MUSE FITS keyword specification.

The specification is the mission keyword sheet, ``specs/keywords.csv``
(:data:`SHEET_PATH`), one row per keyword. An ``X`` in a level column
(``L0``..``L3``) means the card is present in every file of that level; a
keyword is never optional. Each level's ``specs/<level>/_meta.toml`` carries
what the sheet lacks: spec name, version, title, source document and HDU
layout.

Sheet columns:

- ``FITS KW``: the keyword. Trailing padding is stripped. Blank or ``tbd``
  marks an ISP field with no keyword assigned yet; such rows load as
  :attr:`Spec.unassigned` and are never validated.
- ``Type``: ``Integer``/``String``/``Float``/``Boolean``; blank means no type
  check.
- ``Lower Limit``/``Upper Limit``: inclusive numeric range.
- ``FITS Comment``: the card comment (the ISP mnemonic on ISP rows).
- ``Comment``: free-text notes.

Cards the FITS library writes and consumes itself (table structure,
tile-compression bookkeeping, checksums) are flagged ``library_owned``:
astropy hides or rewrites them in ``hdul[1].header``, so the validator and
:func:`example_header` leave them to the library.

The loader checks the sheet against these rules, so a typo in the sheet fails
at load time with its row number, not silently during header validation.
"""

from __future__ import annotations

import csv
import re
import tomllib
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from math import isfinite
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

LEVELS = ("level0", "level1", "level2", "level3")
SHEET = "keywords.csv"
SHEET_PATH = files("muse_fits_specifications") / "specs" / SHEET
"""
The packaged keyword sheet, e.g. ``SHEET_PATH.read_text(encoding="utf-8-sig")`` for the
raw CSV.
"""

_COLUMNS = ("FITS KW", "Type", "Lower Limit", "Upper Limit", "FITS Comment", "Comment")
_TYPES = {"Integer": "int", "String": "str", "Float": "float", "Boolean": "bool", "": None}
_META_FIELDS = ("spec", "spec_version", "title", "source_document")
_KEYWORD = re.compile(r"[A-Z0-9_-]{1,8}")
# Written and consumed by the FITS library (astropy CompImageHDU, checksums): hidden or
# rewritten in hdul[1].header, so never validated. Pinned by test_library_owned_matches_astropy.
_LIBRARY_OWNED = re.compile(
    r"XTENSION|BITPIX|NAXIS\d*|PCOUNT|GCOUNT|TFIELDS|TTYPE\d+|TFORM\d+|Z[A-Z0-9]*|EXTNAME|BZERO|BSCALE|CHECKSUM|DATASUM"
)


class SpecDefinitionError(Exception):
    """
    The keyword sheet or a level's ``_meta.toml`` violates the spec rules.
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


@dataclass(frozen=True)
class HduSpec:
    name: str
    kind: str
    compression: str | None = None


@dataclass(frozen=True)
class Spec:
    name: str
    version: str
    title: str
    source_document: str
    hdus: tuple[HduSpec, ...]
    keywords: Mapping[str, KeywordSpec]
    unassigned: tuple[KeywordSpec, ...] = ()


def _limit(raw: str, kind: str | None, row: int, column: str) -> int | float | None:
    if raw == "":
        return None
    if kind not in ("int", "float"):
        msg = f"row {row}: {column} needs an Integer or Float Type, got {kind!r}"
        raise SpecDefinitionError(msg)
    try:
        value = int(raw) if kind == "int" else float(raw)
    except ValueError:
        msg = f"row {row}: {column} {raw!r} is not a number"
        raise SpecDefinitionError(msg) from None
    if isinstance(value, float) and not isfinite(value):
        msg = f"row {row}: {column} must be finite, got {raw!r}"
        raise SpecDefinitionError(msg)
    return value


def _row(record: Mapping[str, str], row: int) -> KeywordSpec:
    name = record["FITS KW"]
    if name.lower() == "tbd":
        name = ""
    if name and not _KEYWORD.fullmatch(name):
        msg = f"row {row}: {name!r} is not a FITS keyword (1-8 characters of A-Z 0-9 _ -)"
        raise SpecDefinitionError(msg)
    if record["Type"] not in _TYPES:
        msg = f"row {row}: Type must be one of {[t for t in _TYPES if t]} or blank, got {record['Type']!r}"
        raise SpecDefinitionError(msg)
    kind = _TYPES[record["Type"]]
    minimum = _limit(record["Lower Limit"], kind, row, "Lower Limit")
    maximum = _limit(record["Upper Limit"], kind, row, "Upper Limit")
    if minimum is not None and maximum is not None and minimum > maximum:
        msg = f"row {row}: Lower Limit {minimum} exceeds Upper Limit {maximum}"
        raise SpecDefinitionError(msg)
    return KeywordSpec(
        name=name,
        type=kind,
        minimum=minimum,
        maximum=maximum,
        comment=record["FITS Comment"],
        notes=record["Comment"],
        library_owned=bool(_LIBRARY_OWNED.fullmatch(name)),
    )


def parse_sheet(lines: Iterable[str]) -> list[tuple[frozenset[str], KeywordSpec]]:
    """
    Parse the keyword sheet into ``(levels, keyword)`` pairs, in sheet order.

    ``levels`` holds the level names whose column is marked ``X``. Blank rows are
    skipped; header names are matched with whitespace collapsed.
    """
    reader = csv.reader(lines, strict=True)
    try:
        return _parse_sheet(reader)
    except csv.Error as exc:
        msg = f"row {reader.line_num}: invalid CSV: {exc}"
        raise SpecDefinitionError(msg) from exc


def _parse_sheet(reader) -> list[tuple[frozenset[str], KeywordSpec]]:
    header = [" ".join(cell.split()) for cell in next(reader, [])]
    level_columns = {f"L{level.removeprefix('level')}": level for level in LEVELS}
    expected = ("ISP", *level_columns, *_COLUMNS)
    missing = [column for column in expected if column not in header]
    if missing:
        msg = f"sheet is missing columns {missing}"
        raise SpecDefinitionError(msg)
    unexpected = [column for column in header if column not in expected]
    if unexpected:
        msg = f"sheet has unexpected columns {unexpected}"
        raise SpecDefinitionError(msg)
    if len(header) != len(set(header)):
        msg = "sheet has duplicate columns"
        raise SpecDefinitionError(msg)
    rows = []
    for cells in reader:
        if not any(cell.strip() for cell in cells):
            continue
        if len(cells) != len(header):
            msg = f"row {reader.line_num}: expected {len(header)} cells, got {len(cells)}"
            raise SpecDefinitionError(msg)
        record = dict(zip(header, (cell.strip() for cell in cells), strict=True))
        for column in ("ISP", *level_columns):
            if record[column].upper() not in ("", "X"):
                msg = f"row {reader.line_num}: {column} must be X or blank, got {record[column]!r}"
                raise SpecDefinitionError(msg)
        levels = frozenset(level for column, level in level_columns.items() if record[column].upper() == "X")
        if not levels:
            msg = f"row {reader.line_num}: not marked for any level"
            raise SpecDefinitionError(msg)
        rows.append((levels, _row(record, reader.line_num)))
    return rows


@cache
def load_sheet() -> tuple[tuple[frozenset[str], KeywordSpec], ...]:
    """
    The packaged sheet as ``(levels, keyword)`` pairs, in sheet order.
    """
    with SHEET_PATH.open(encoding="utf-8-sig") as lines:
        return tuple(parse_sheet(lines))


def _collect(
    rows: Iterable[tuple[frozenset[str], KeywordSpec]], level: str
) -> tuple[dict[str, KeywordSpec], tuple[KeywordSpec, ...]]:
    """
    Split the sheet's rows for ``level`` into keywords and unassigned fields.
    """
    keywords: dict[str, KeywordSpec] = {}
    unassigned: list[KeywordSpec] = []
    for levels, kw in rows:
        if level not in levels:
            continue
        if not kw.name:
            unassigned.append(kw)
        elif kw.name in keywords:
            msg = f"{SHEET}: {kw.name} is listed twice for {level}"
            raise SpecDefinitionError(msg)
        else:
            keywords[kw.name] = kw
    if not keywords:
        msg = f"{SHEET}: no keywords marked for {level}"
        raise SpecDefinitionError(msg)
    return keywords, tuple(unassigned)


def _meta_path(level: str):
    return files("muse_fits_specifications") / "specs" / level / "_meta.toml"


def defined_levels() -> tuple[str, ...]:
    """
    The levels that have a ``specs/<level>/_meta.toml``, in :data:`LEVELS` order.
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
        ):
            msg = f"{source}: each [[hdus]] table needs string name and kind, optionally compression; got {hdu!r}"
            raise SpecDefinitionError(msg)
    return meta


@cache
def load_spec(level: str) -> Spec:
    """
    Load one level's specification, e.g. ``load_spec("level0")``.
    """
    if level not in LEVELS:
        msg = f"unknown level {level!r}; expected one of {LEVELS}"
        raise ValueError(msg)
    keywords, unassigned = _collect(load_sheet(), level)
    source = f"specs/{level}/_meta.toml"
    if level not in defined_levels():
        msg = f"{source} does not exist; add it to define {level}"
        raise SpecDefinitionError(msg)
    meta = _parse_meta(_meta_path(level).read_text(encoding="utf-8"), source)
    return Spec(
        name=meta["spec"],
        version=meta["spec_version"],
        title=meta["title"],
        source_document=meta["source_document"],
        hdus=tuple(HduSpec(h["name"], h["kind"], h.get("compression")) for h in meta["hdus"]),
        keywords=MappingProxyType(keywords),
        unassigned=unassigned,
    )


_PLACEHOLDERS = {"bool": False, "int": 0, "float": 0.0, "str": "UNKNOWN", None: 0}


def example_header(spec: Spec) -> dict[str, bool | int | float | str]:
    """
    A conforming header: one value for every keyword the mission writes.

    Generators (simulators, fixture writers) start from this so their files conform to
    the same spec the validator enforces. Values are the sheet's lower limit where there
    is one, otherwise a neutral typed placeholder (``0``/``0.0``/``UNKNOWN``; presence-
    only keywords get ``0``). Library-owned cards are left to the FITS library. The
    result passes :func:`validate`.
    """
    return {
        name: kw.minimum if kw.minimum is not None else _PLACEHOLDERS[kw.type]
        for name, kw in spec.keywords.items()
        if not kw.library_owned
    }
