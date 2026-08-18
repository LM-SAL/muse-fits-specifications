"""
Render the packaged specs as reStructuredText reference pages.

Regenerate after editing a spec YAML so the docs cannot drift from the spec.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .spec import LEVELS, Spec, load_spec


def _cell(text: object) -> str:
    """
    Escape rst inline markup so arbitrary spec text is safe in a table cell.
    """
    if not text:
        return ""
    escaped = str(text).replace("\\", "\\\\").replace("\n", " ")
    for char in "*`|_":
        escaped = escaped.replace(char, "\\" + char)
    return escaped


def _heading(text: str, char: str) -> list[str]:
    return [text, char * len(text), ""]


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    lines = [".. list-table::", "   :header-rows: 1", ""]
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
    ]
    required = sum(1 for kw in spec.keywords.values() if kw.required)
    lines += _heading(f"Keywords ({len(spec.keywords)} total, {required} required)", "-")
    for section in spec.sections:
        keywords = [kw for kw in spec.keywords.values() if kw.section == section]
        rows = []
        for kw in keywords:
            constraints = []
            if kw.values is not None:
                constraints.append("one of " + ", ".join(map(str, kw.values)))
            if kw.format:
                constraints.append(kw.format)
            rows.append(
                [
                    _cell(kw.name),
                    "yes" if kw.required else "",
                    _cell(kw.type),
                    _cell("; ".join(constraints)),
                    _cell(kw.source),
                    _cell(kw.example),
                    _cell(kw.comment),
                ]
            )
        lines += _heading(f"{section} ({len(keywords)})", "~")
        lines += _table(
            ["Keyword", "Required", "Type", "Constraints", "Source", "Example", "Comment"],
            rows,
        )
    return "\n".join(lines).rstrip("\n") + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        return 2
    out = Path(argv[0])
    out.mkdir(parents=True, exist_ok=True)
    for level in LEVELS:
        spec = load_spec(level)
        path = out / f"{level}.rst"
        path.write_text(render_spec(spec))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
