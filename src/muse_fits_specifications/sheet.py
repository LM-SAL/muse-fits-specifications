"""
Convert the mission keyword sheet into the YAML that the loader and the docs read.

The team edits the "MUSE FITS Keyword Master" spreadsheet and exports it over
``specs/keywords.csv`` (:data:`~muse_fits_specifications.spec.SHEET_PATH`); ``python -m
muse_fits_specifications.sheet`` then rewrites ``specs/keywords/``
(:data:`~muse_fits_specifications.spec.KEYWORDS_PATH`): one YAML file per sheet section,
named after its title (``untitled.yml`` for the rows above the first section row), and
``_sections.yml``, which lists them in sheet order. All of it is committed, so a review
reads the YAML diff, which shows which topics an export changed however the spreadsheet
reordered or quoted the CSV. ``python -m muse_fits_specifications`` fails while the YAML
is stale.

Sheet rules:

- A row whose ``FITS KW`` starts with ``#`` is a section row: its ``Type`` cell names the
  section of the rows below it; a blank ``Type`` makes it a spacer.
- ``FITS KW``: 1-8 characters of ``A-Z0-9_-``; padding is stripped. Blank or ``tbd``
  marks an ISP field with no keyword yet, listed as unassigned and never validated.
- ``Type``: ``str``, ``bool``, ``int``, ``float``, ``float32``, ``float64``,
  ``ISO 8601`` (a string), or a sized integer such as ``uint16`` or ``int16``, whose range
  bounds the row's limits and values and fills a blank limit.
- ``L0``..``L3``: ``X`` when every file of the level carries the card, ``CI`` or ``SG``
  when only that camera type's files do, blank otherwise. A row with no level is parked:
  it stays in the YAML and on the keywords page but in no level.
- ``Lower Limit``: a number, the inclusive minimum; or ``;``-separated allowed values,
  with surrounding double quotes dropped and booleans written ``T``/``F``.
- ``Upper Limit``: the inclusive maximum, for a numeric ``Type`` without allowed values.
- ``FITS Comment``, ``Comment`` and ``ISP mnemonic`` become the card comment, notes and
  mnemonic; ``ISP`` is not used.

A keyword may appear once per level and camera type. Every row error names its CSV
row; column errors name the columns.
"""

from __future__ import annotations

import csv
import io
import re
import sys
from math import isfinite
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from .spec import (
    FAMILIES,
    KEYWORDS,
    KEYWORDS_PATH,
    LEVELS,
    SECTIONS,
    SHEET,
    SHEET_PATH,
    SpecDefinitionError,
    defined_levels,
    families,
    load_sheet,
    load_spec,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

_LEVEL_COLUMNS = {f"L{level.removeprefix('level')}": level for level in LEVELS}
_COLUMNS = (
    "FITS KW",
    "Type",
    "ISP",
    *_LEVEL_COLUMNS,
    "Lower Limit",
    "Upper Limit",
    "FITS Comment",
    "Comment",
    "ISP mnemonic",
)
_TYPES = {"str": "str", "bool": "bool", "int": "int", "float": "float", "float32": "float", "float64": "float"}
_ISO = "ISO 8601"
_SIZED_INT = re.compile(r"(u?)int(8|16|32|64)")
_KEYWORD = re.compile(r"[A-Z0-9_-]{1,8}")
# Written and consumed by the FITS library (astropy CompImageHDU, checksums): hidden or
# rewritten in hdul[1].header, so never validated. Pinned by test_library_owned_matches_astropy.
_LIBRARY_OWNED = re.compile(
    r"XTENSION|BITPIX|NAXIS\d*|PCOUNT|GCOUNT|TFIELDS|TTYPE\d+|TFORM\d+|Z[A-Z0-9]*|EXTNAME|BZERO|BSCALE|CHECKSUM|DATASUM"
)
_HEADER = (
    "# Generated from keywords.csv by `python -m muse_fits_specifications.sheet`; edit the sheet, not this file.\n"
)


def _type(raw: str, row: int) -> tuple[str | None, tuple[int, int] | None]:
    """
    The validator type for a sheet ``Type``, and the range of a sized integer.
    """
    if sized := _SIZED_INT.fullmatch(raw):
        bits = int(sized[2])
        return "int", (0, 2**bits - 1) if sized[1] else (-(2 ** (bits - 1)), 2 ** (bits - 1) - 1)
    if raw == _ISO:
        return "str", None
    if raw == "":
        return None, None
    if raw not in _TYPES:
        msg = f"row {row}: Type must be one of {[*_TYPES, _ISO]}, a sized integer such as uint16, or blank; got {raw!r}"
        raise SpecDefinitionError(msg)
    return _TYPES[raw], None


def _number(raw: str, kind: str, row: int, column: str) -> int | float:
    if "_" in raw:  # Python reads 1_000 as 1000; a spreadsheet number never has one
        msg = f"row {row}: {column} {raw!r} is not a number"
        raise SpecDefinitionError(msg)
    try:
        value = int(raw) if kind == "int" else float(raw)
    except ValueError:
        msg = f"row {row}: {column} {raw!r} is not {'an integer' if kind == 'int' else 'a number'}"
        raise SpecDefinitionError(msg) from None
    if not isfinite(value):
        msg = f"row {row}: {column} must be finite, got {raw!r}"
        raise SpecDefinitionError(msg)
    return value


def _value(raw: str, kind: str, row: int) -> bool | int | float | str:
    if kind == "bool":
        if raw not in ("T", "F"):
            msg = f"row {row}: a bool value must be T or F, got {raw!r}"
            raise SpecDefinitionError(msg)
        return raw == "T"
    return raw if kind == "str" else _number(raw, kind, row, "Lower Limit")


def _limits(record: dict[str, str], kind: str | None, bounds: tuple[int, int] | None, row: int) -> dict:
    """
    The row's allowed values or its inclusive minimum and maximum.
    """
    lower, upper = record["Lower Limit"], record["Upper Limit"]
    if kind is None:
        if lower or upper:
            msg = f"row {row}: limits need a Type"
            raise SpecDefinitionError(msg)
        return {}
    numeric = kind in ("int", "float")
    values = minimum = maximum = None
    if numeric and ";" not in lower:
        minimum = _number(lower, kind, row, "Lower Limit") if lower else None
    elif lower:
        parts = (part.strip().strip('"').strip() for part in lower.split(";"))
        values = [_value(part, kind, row) for part in parts if part]
        if not values:
            msg = f"row {row}: Lower Limit {lower!r} lists no values"
            raise SpecDefinitionError(msg)
    if upper:
        if not numeric or values is not None:
            msg = f"row {row}: Upper Limit needs a numeric Type and a numeric Lower Limit or none"
            raise SpecDefinitionError(msg)
        maximum = _number(upper, kind, row, "Upper Limit")
    if minimum is not None and maximum is not None and minimum > maximum:
        msg = f"row {row}: Lower Limit {minimum} exceeds Upper Limit {maximum}"
        raise SpecDefinitionError(msg)
    if bounds:
        for number in values if values is not None else (minimum, maximum):
            if isinstance(number, int) and not bounds[0] <= number <= bounds[1]:
                msg = f"row {row}: {number} is outside the {record['Type']} range {bounds[0]} to {bounds[1]}"
                raise SpecDefinitionError(msg)
        if values is None:
            minimum = bounds[0] if minimum is None else minimum
            maximum = bounds[1] if maximum is None else maximum
    return {"minimum": minimum, "maximum": maximum, "values": values}


def _keyword(record: dict[str, str], row: int) -> dict:
    name = record["FITS KW"]
    if name.lower() == "tbd":
        name = ""
    if name and not _KEYWORD.fullmatch(name):
        msg = f"row {row}: {name!r} is not a FITS keyword (1-8 characters of A-Z 0-9 _ -)"
        raise SpecDefinitionError(msg)
    levels = {}
    for column, level in _LEVEL_COLUMNS.items():
        marker = record[column].upper()
        if marker not in ("", "X", *FAMILIES):
            msg = f"row {row}: {column} must be X, {', '.join(FAMILIES)} or blank, got {record[column]!r}"
            raise SpecDefinitionError(msg)
        if marker:
            levels[level] = "all" if marker == "X" else marker
    kind, bounds = _type(record["Type"], row)
    entry = {
        "name": name,
        "levels": levels,
        "type": kind,
        "format": "isot" if record["Type"] == _ISO else None,
        **_limits(record, kind, bounds, row),
        "mnemonic": record["ISP mnemonic"],
        "comment": record["FITS Comment"],
        "notes": record["Comment"],
        "library_owned": True if name and _LIBRARY_OWNED.fullmatch(name) else None,
    }
    return {key: value for key, value in entry.items() if key == "name" or value not in (None, "")}


def convert(lines: Iterable[str]) -> list[dict]:
    """
    Convert the sheet's CSV lines into its sections, in sheet order.

    Each section is ``{"section": title, "keywords": [...]}``; rows above the first
    section row form an untitled section. Raises
    :class:`~muse_fits_specifications.spec.SpecDefinitionError` on any broken sheet rule,
    naming the row, including two sections whose titles give one file name.
    """
    reader = csv.reader(lines, strict=True)
    try:
        return _convert(reader)
    except csv.Error as exc:
        msg = f"row {reader.line_num}: invalid CSV: {exc}"
        raise SpecDefinitionError(msg) from exc


def _convert(reader) -> list[dict]:
    header = [" ".join(cell.split()) for cell in next(reader, [])]
    missing = [column for column in _COLUMNS if column not in header]
    if missing:
        msg = f"sheet is missing columns {missing}"
        raise SpecDefinitionError(msg)
    unexpected = [column for column in header if column not in _COLUMNS]
    if unexpected:
        msg = f"sheet has unexpected columns {unexpected}"
        raise SpecDefinitionError(msg)
    if len(header) != len(set(header)):
        msg = "sheet has duplicate columns"
        raise SpecDefinitionError(msg)
    sections: list[dict] = [{"section": "", "keywords": []}]
    heading_rows = [0]
    first_rows: dict[tuple[str, str, str], int] = {}
    for cells in reader:
        if not any(cell.strip() for cell in cells):
            continue
        row = reader.line_num
        if len(cells) != len(header):
            msg = f"row {row}: expected {len(header)} cells, got {len(cells)}"
            raise SpecDefinitionError(msg)
        record = dict(zip(header, (cell.strip() for cell in cells), strict=True))
        if record["FITS KW"].startswith("#"):
            if record["Type"]:
                sections.append({"section": record["Type"], "keywords": []})
                heading_rows.append(row)
            continue
        keyword = _keyword(record, row)
        for level, marker in keyword["levels"].items():
            for family in FAMILIES if marker == "all" else (marker,):
                first = first_rows.setdefault((keyword["name"], level, family), row)
                if keyword["name"] and first != row:
                    msg = f"row {row}: {keyword['name']} is already listed for {level} on row {first}"
                    raise SpecDefinitionError(msg)
        sections[-1]["keywords"].append(keyword)
    kept = [(section, row) for section, row in zip(sections, heading_rows, strict=True) if section["keywords"]]
    file_rows: dict[str, int] = {}
    for section, row in kept:
        first = file_rows.setdefault(section_file(section["section"]), row)
        if first != row:
            where = f"the section on row {first}" if first else "the rows above the first section row"
            msg = f"row {row}: section {section['section']!r} has the same file name as {where}"
            raise SpecDefinitionError(msg)
    return [section for section, _ in kept]


def section_file(title: str) -> str:
    """
    The YAML file name of the sheet section ``title``, e.g. ``exposure-and-timing.yml``.
    """
    return (re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "untitled") + ".yml"


def _yaml(value: object, *, flow: bool | None = None) -> str:
    return _HEADER + yaml.safe_dump(
        value, sort_keys=False, allow_unicode=True, width=float("inf"), default_flow_style=flow
    )


def dump(sections: list[dict]) -> dict[str, str]:
    """
    The files of ``specs/keywords/`` for :func:`convert`'s sections, by name: one per
    section and ``_sections.yml``, their order.
    """
    files = {section_file(section["section"]): _yaml(section) for section in sections}
    return {SECTIONS: _yaml(list(files), flow=False), **files}  # one line per file, so an inserted section is one line


def write(directory: Path, files: dict[str, str]) -> None:
    """
    Write :func:`dump`'s ``files`` into ``directory`` and delete any other ``*.yml``
    there.
    """
    directory.mkdir(parents=True, exist_ok=True)
    for stale in directory.glob("*.yml"):
        if stale.name not in files:
            stale.unlink()
    for name, text in files.items():
        (directory / name).write_text(text, encoding="utf-8", newline="\n")


def check() -> int:
    """
    Check the packaged sheet, its YAML and every defined level; run as ``python -m
    muse_fits_specifications``.

    Raises :class:`~muse_fits_specifications.spec.SpecDefinitionError` when the sheet
    breaks a rule, ``specs/keywords/`` is not what the sheet converts to, the sheet marks
    a level that has no ``_meta.toml``, or a level fails to load. Run by pre-commit on
    spec changes and by the tests.
    """
    expected = dump(convert(io.StringIO(SHEET_PATH.read_text(encoding="utf-8-sig"))))
    packaged = {
        entry.name: entry.read_text(encoding="utf-8")
        for entry in KEYWORDS_PATH.iterdir()
        if entry.name.endswith(".yml")
    }
    stale = sorted(name for name in expected.keys() | packaged.keys() if expected.get(name) != packaged.get(name))
    if stale:
        msg = f"specs/keywords/ does not match specs/keywords.csv ({', '.join(stale)}); run python -m muse_fits_specifications.sheet"
        raise SpecDefinitionError(msg)
    marked = {level for levels, _ in load_sheet() for level in levels}
    undefined = [level for level in LEVELS if level in marked and level not in defined_levels()]
    if undefined:
        msg = f"keywords.csv marks {undefined} but specs/<level>/_meta.toml is missing"
        raise SpecDefinitionError(msg)
    for level in defined_levels():
        for family in families(level):
            load_spec(level, family)
    return 0


def main() -> int:
    """
    Rewrite ``specs/keywords/`` in the source tree from ``specs/keywords.csv``.
    """
    specs = Path(__file__).with_name("specs")
    write(specs / KEYWORDS, dump(convert(io.StringIO((specs / SHEET).read_text(encoding="utf-8-sig")))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
