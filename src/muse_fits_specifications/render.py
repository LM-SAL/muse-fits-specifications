"""
Render the packaged specs as reStructuredText reference pages.

Runs at docs build time, so the pages cannot drift from the keyword sheet.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from .spec import LEVELS, SHEET, SHEET_PATH, Spec, defined_levels, load_sheet, load_spec

if TYPE_CHECKING:
    from collections.abc import Sequence

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


def render_spec(spec: Spec) -> str:
    lines = [
        *_heading(spec.title, "="),
        f"Spec ``{spec.name}`` version {spec.version}.",
        f"Source: {spec.source_document}.",
        "",
        *_heading("HDUs", "-"),
        *_table(
            ["Name", "Kind", "Compression"],
            [[hdu.name, hdu.kind, _cell(hdu.compression)] for hdu in spec.hdus],
        ),
        *_heading(f"Keywords ({len(spec.keywords)})", "-"),
        "Every keyword is present in every file of this level, in sheet order.",
        "Library-owned cards are excluded from these checks; checksum verification must be enabled separately when opening the file.",
        "",
        *_table(
            ["Keyword", "Type", "Min", "Max", "FITS comment", "Notes", "Library-owned"],
            [
                [
                    _cell(kw.name),
                    _cell(kw.type),
                    _cell(kw.minimum),
                    _cell(kw.maximum),
                    _cell(kw.comment),
                    _cell(kw.notes),
                    "yes" if kw.library_owned else "",
                ]
                for kw in spec.keywords.values()
            ],
            widths="11 7 11 11 20 32 8",
        ),
    ]
    if spec.unassigned:
        lines += [
            *_heading(f"Unassigned ISP fields ({len(spec.unassigned)})", "-"),
            "ISP fields the sheet lists for this level without a FITS keyword yet; not validated.",
            "",
            *_table(
                ["ISP mnemonic", "Type", "Min", "Max", "Notes"],
                [
                    [_cell(kw.comment), _cell(kw.type), _cell(kw.minimum), _cell(kw.maximum), _cell(kw.notes)]
                    for kw in spec.unassigned
                ],
                widths="30 8 12 12 38",
            ),
        ]
    return "\n".join(lines).rstrip("\n") + "\n"


def render_sheet(rows: Sequence[tuple[frozenset[str], KeywordSpec]]) -> str:
    """
    The whole sheet as one table with an X column per level, in sheet order.
    """
    lines = [
        *_heading("Keywords", "="),
        f":download:`Download the keyword CSV <{SHEET}>`.",
        "",
        f"Every row of ``specs/{SHEET}`` in sheet order.",
        "An X marks the levels whose files carry the card; a row without a keyword is an ISP field not yet assigned one.",
        "",
        *_heading(f"Rows ({len(rows)})", "-"),
        *_table(
            [
                *("L" + level.removeprefix("level") for level in LEVELS),
                "Keyword",
                "Type",
                "Min",
                "Max",
                "FITS comment",
                "Notes",
            ],
            [
                [
                    *("X" if level in levels else "" for level in LEVELS),
                    _cell(kw.name),
                    _cell(kw.type),
                    _cell(kw.minimum),
                    _cell(kw.maximum),
                    _cell(kw.comment),
                    _cell(kw.notes),
                ]
                for levels, kw in rows
            ],
            widths="4 4 4 4 10 6 11 11 18 28",
        ),
    ]
    return "\n".join(lines).rstrip("\n") + "\n"


def main(argv: list[str]) -> int:
    """
    Write the sheet, ``keywords.rst`` and ``<level>.rst`` for every defined level into
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
    for level in defined_levels():
        (out / f"{level}.rst").write_text(render_spec(load_spec(level)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
