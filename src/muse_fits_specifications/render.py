"""
Render the packaged specs as reStructuredText reference pages.

Runs at docs build time and reads the YAML in ``specs/keywords/``, so the pages cannot
drift from the keyword sheet.
"""

from __future__ import annotations

import sys
from itertools import groupby
from pathlib import Path
from typing import TYPE_CHECKING

from .spec import (
    KEYWORDS,
    LEVELS,
    SHEET,
    SHEET_PATH,
    Spec,
    defined_levels,
    families,
    load_sheet,
    load_spec,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

    from .spec import KeywordSpec


def _cell(text: object) -> str:
    """
    Escape rst inline markup so arbitrary spec text is safe in a table cell.
    """
    if text is None:
        return ""
    escaped = str(text).replace("\\", "\\\\").replace("\n", " ")
    for char in "*`|_":
        escaped = escaped.replace(char, "\\" + char)
    return escaped


def _heading(text: str, char: str) -> list[str]:
    return [text, char * len(text), ""]


def _table(header: list[str], rows: list[list[str]], *, widths: str = "auto") -> list[str]:
    lines = [".. list-table::", "   :header-rows: 1", f"   :widths: {widths}", ""]
    if widths != "auto":
        lines.insert(-1, "   :class: keyword-table")
    for row in [header, *rows]:
        for index, cell in enumerate(row):
            prefix = "   * - " if index == 0 else "     - "
            lines.append((prefix + cell).rstrip())
    lines.append("")
    return lines


def _sectioned[T](
    items: Iterable[T], section: Callable[[T], str], header: list[str], row: Callable[[T], list[str]], widths: str
) -> list[str]:
    """
    One table per sheet section, under the section's title; untitled rows get no
    heading.
    """
    lines = []
    for title, group in groupby(items, key=section):
        lines += [
            *(_heading(title, "^") if title else []),
            *_table(header, [row(item) for item in group], widths=widths),
        ]
    return lines


def _type(kw: KeywordSpec) -> str:
    return "str (ISO 8601)" if kw.format == "isot" else _cell(kw.type)


def _allowed(kw: KeywordSpec) -> str:
    """
    The allowed values, or the inclusive range, as one cell.
    """
    if kw.values is not None:
        text = "; ".join(str(value) for value in kw.values)
    elif kw.minimum is not None and kw.maximum is not None:
        text = f"{kw.minimum} to {kw.maximum}"
    elif kw.minimum is not None:
        text = f">= {kw.minimum}"
    else:
        text = f"<= {kw.maximum}" if kw.maximum is not None else ""
    return _cell(text)


def page_title(spec: Spec) -> str:
    """
    The level's title, plus its camera type for a level whose CI and SG files differ.
    """
    return f"{spec.title} ({spec.family})" if spec.family else spec.title


def level_pages() -> list[tuple[str, Spec]]:
    """
    ``(docname, spec)`` for every defined level and camera type, e.g. ``"level1-sg"``.
    """
    return [
        (level if family is None else f"{level}-{family.lower()}", load_spec(level, family))
        for level in defined_levels()
        for family in families(level)
    ]


def render_spec(spec: Spec) -> str:
    files = f"{spec.family} files" if spec.family else "files"
    lines = [
        *_heading(page_title(spec), "="),
        f"Spec ``{spec.name}`` version {spec.version}.",
        f"Source: {spec.source_document}.",
        "",
        *_heading("HDUs", "-"),
        "The extensions that follow the empty primary HDU, in file order.",
        "",
        *_table(
            ["Name", "Kind", "Compression"],
            [[_cell(hdu.name), _cell(hdu.kind), _cell(hdu.compression)] for hdu in spec.hdus],
        ),
        *_heading(f"Keywords ({len(spec.keywords)})", "-"),
        f"Every keyword is present in every one of this level's {files}, in sheet order.",
        "Library-owned cards are excluded from these checks; checksum verification must be enabled separately when opening the file.",
        "",
        *_sectioned(
            spec.keywords.values(),
            lambda kw: kw.section,
            ["Keyword", "Type", "Allowed", "FITS comment", "ISP mnemonic", "Notes", "Library-owned"],
            lambda kw: [
                _cell(kw.name),
                _type(kw),
                _allowed(kw),
                _cell(kw.comment),
                _cell(kw.mnemonic),
                _cell(kw.notes),
                "yes" if kw.library_owned else "",
            ],
            "11 9 13 19 18 22 8",
        ),
    ]
    if spec.unassigned:
        lines += [
            *_heading(f"Unassigned ISP fields ({len(spec.unassigned)})", "-"),
            "ISP fields the sheet lists for this level without a FITS keyword yet; not validated.",
            "",
            *_table(
                ["ISP mnemonic", "Type", "Allowed", "FITS comment", "Notes"],
                [
                    [_cell(kw.mnemonic), _type(kw), _allowed(kw), _cell(kw.comment), _cell(kw.notes)]
                    for kw in spec.unassigned
                ],
                widths="24 9 14 23 30",
            ),
        ]
    return "\n".join(lines).rstrip("\n") + "\n"


def render_sheet(rows: Sequence[tuple[Mapping[str, str], KeywordSpec]]) -> str:
    """
    The whole sheet with a column per level, one table per section, in sheet order.
    """
    lines = [
        *_heading("Keywords", "="),
        f":download:`Download the keyword sheet <{SHEET}>`.",
        "",
        f"Every row of ``specs/{SHEET}`` in sheet order, as the YAML in ``specs/{KEYWORDS}/`` records it, one file per section.",
        "A level column holds X when every file of the level carries the card, and CI or SG when only that camera type's files do.",
        "A row without a keyword is an ISP field not yet assigned one; a row without a level is parked and not validated.",
        "",
        *_heading(f"Rows ({len(rows)})", "-"),
        *_sectioned(
            rows,
            lambda row: row[1].section,
            [
                *("L" + level.removeprefix("level") for level in LEVELS),
                "Keyword",
                "Type",
                "Allowed",
                "FITS comment",
                "ISP mnemonic",
                "Notes",
            ],
            lambda row: [
                *("X" if row[0].get(level) == "all" else row[0].get(level, "") for level in LEVELS),
                _cell(row[1].name),
                _type(row[1]),
                _allowed(row[1]),
                _cell(row[1].comment),
                _cell(row[1].mnemonic),
                _cell(row[1].notes),
            ],
            "4 4 4 4 10 8 12 16 16 22",
        ),
    ]
    return "\n".join(lines).rstrip("\n") + "\n"


def main(argv: list[str]) -> int:
    """
    Write the sheet, ``keywords.rst`` and one page per :func:`level_pages` entry into
    ``argv[0]``.

    Level pages left over from a level that is no longer defined are removed.
    """
    if len(argv) != 1:
        return 2
    out = Path(argv[0])
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob("level*.rst"):
        stale.unlink()
    (out / SHEET).write_bytes(SHEET_PATH.read_bytes())
    (out / "keywords.rst").write_text(render_sheet(load_sheet()))
    for docname, spec in level_pages():
        (out / f"{docname}.rst").write_text(render_spec(spec))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
