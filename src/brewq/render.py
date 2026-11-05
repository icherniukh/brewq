from __future__ import annotations

import os
import shutil
import sys
import textwrap
from typing import TextIO

from brewq.columns import ColumnDef
from brewq.model import Package

# ANSI escape sequences. Standard 16-color codes are used throughout so
# package/status colors follow the user's terminal theme instead of pinning
# fixed 256-color values.
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"
_COLOR_GREEN = "\033[32m"
_COLOR_FORMULA = "\033[36m"  # cyan
_COLOR_CASK = "\033[35m"     # magenta
_COLOR_DEPRECATED = "\033[33m"  # yellow
_COLOR_DISABLED = "\033[31m"    # red


def _trend_emphasis(pkg: Package) -> tuple[str, str]:
    """Table-only momentum cues; keep the column registry and TSV numeric."""
    trend = pkg.trending
    if trend is None:
        return "", _DIM
    # Match the displayed precision so a visible 2.0x always gets the hot cue.
    trend = round(trend, 1)
    if trend >= 2:
        return "↑↑", _BOLD + _COLOR_GREEN
    if trend >= 1.2:
        return "↑", _COLOR_GREEN
    if trend < 0.8:
        return "↓", _DIM
    return "·", _DIM


def render_cache_note(message: str, out: TextIO) -> None:
    """Keep routine cache health visible but subordinate to query results."""
    if _use_color(out):
        out.write(_DIM + message + _RESET + "\n")
    else:
        out.write(message + "\n")


def _plain_status_prefix(pkg: Package) -> str:
    if pkg.disabled:
        return "(disabled) "
    if pkg.deprecated:
        return "(deprecated) "
    return ""


def _use_color(out: TextIO) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return hasattr(out, "isatty") and out.isatty()


def _terminal_width() -> int:
    return shutil.get_terminal_size((100, 24)).columns


def _wrap(text: str, width: int) -> list[str]:
    if not text or width <= 0:
        return [text or ""]
    return textwrap.wrap(text, width) or [""]


def _clip(text: str, width: int) -> str:
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width == 1:
        return "…"
    return text[:width - 1].rstrip() + "…"


def _clip_name(text: str, width: int) -> str:
    if len(text) > width and "/" in text and width >= 3:
        prefix, name = text.rsplit("/", 1)
        if len(name) + 2 > width:
            return "…/" + _clip(name, width - 2)
        return _clip(prefix, width - len(name) - 1) + "/" + name
    return _clip(text, width)


def _status_prefix(pkg: Package, color: bool) -> str:
    text = _plain_status_prefix(pkg)
    if not text or not color:
        return text
    if pkg.disabled:
        return f"{_COLOR_DISABLED}{text}{_RESET}"
    if pkg.deprecated:
        return f"{_COLOR_DEPRECATED}{text}{_RESET}"
    return ""


def render_table(
    packages: list[Package],
    columns: list[ColumnDef],
    out: TextIO | None = None,
    sorted_col: str | None = None,
) -> None:
    if out is None:
        out = sys.stdout
    color = _use_color(out)
    term_width = max(1, _terminal_width())

    # Compute raw cell values
    rows: list[list[str]] = [
        [
            col.getter(pkg) + f" {_trend_emphasis(pkg)[0]:<2}"
            if col.key == "trending" else col.getter(pkg)
            for col in columns
        ]
        for pkg in packages
    ]
    headers = [
        (col.header + " ↓" if sorted_col and col.key == sorted_col else col.header)
        for col in columns
    ]

    # Find description column index (wrappable)
    desc_idx = next(
        (i for i, col in enumerate(columns) if col.key == "description"),
        None,
    )
    name_idx = next((i for i, col in enumerate(columns) if col.key == "name"), None)

    # Compute column widths from content (header or data)
    widths = [len(h) for h in headers]
    for pkg, row in zip(packages, rows, strict=False):
        for i, cell in enumerate(row):
            if i != desc_idx:
                visible_width = len(cell)
                if i == name_idx and pkg.installed:
                    visible_width += 2
                widths[i] = max(widths[i], visible_width)

    gaps = 2 * max(0, len(columns) - 1)
    minimums = [len(header) for header in headers]
    if name_idx is not None:
        minimums[name_idx] = max(minimums[name_idx], min(8, widths[name_idx]))

    # If even the labels cannot fit, keep all selected fields in a readable
    # vertical layout rather than overflowing or silently dropping columns.
    if sum(minimums) + gaps > term_width:
        out.write("\n")
        for pkg, row in zip(packages, rows, strict=False):
            for col, header, cell in zip(columns, headers, row, strict=False):
                if col.key == "name" and pkg.installed:
                    cell += " ✔"
                if col.key == "description" and not any(c.key == "status" for c in columns):
                    cell = _plain_status_prefix(pkg) + cell
                out.write("\n".join(_wrap(f"{header}: {cell}", term_width)) + "\n")
            out.write("\n")
        return

    # A single long tap/name must not monopolize the entire table.
    if name_idx is not None and len(columns) > 1:
        widths[name_idx] = min(widths[name_idx], max(minimums[name_idx], term_width // 4))
    if desc_idx is not None:
        max_content = max((len(row[desc_idx]) for row in rows), default=0)
        widths[desc_idx] = max(minimums[desc_idx], min(max_content, max(20, term_width // 3)))

    # Reserve description context before reducing oversized metadata cells.
    excess = max(0, sum(widths) + gaps - term_width)
    for i in sorted(
        (i for i in range(len(columns)) if i != desc_idx),
        key=lambda i: widths[i] - minimums[i], reverse=True,
    ):
        reduction = min(excess, widths[i] - minimums[i])
        widths[i] -= reduction
        excess -= reduction
    if desc_idx is not None:
        fixed_width = sum(widths[i] for i in range(len(columns)) if i != desc_idx)
        widths[desc_idx] = max(minimums[desc_idx], min(max_content, term_width - fixed_width - gaps))

    # Header
    header_parts = []
    for i, (col, w) in enumerate(zip(columns, widths, strict=False)):
        if i == desc_idx or col.align == "left":
            header_parts.append(f"{headers[i]:<{w}}")
        else:
            header_parts.append(f"{headers[i]:>{w}}")
    separator = "─" * (sum(widths) + gaps)

    out.write("\n")
    if color:
        out.write(_BOLD + "  ".join(header_parts) + _RESET + "\n")
    else:
        out.write("  ".join(header_parts) + "\n")
    out.write(separator + "\n")

    # Rows
    status_idx = next((i for i, c in enumerate(columns) if c.key == "status"), None)
    show_status_in_description = status_idx is None

    for pkg, row in zip(packages, rows, strict=False):
        pkg_type = pkg.type
        is_installed = pkg.installed

        # Include status text in the description's width budget before styling.
        if desc_idx is not None:
            plain_prefix = _plain_status_prefix(pkg) if show_status_in_description else ""
            desc_text = plain_prefix + row[desc_idx]
            desc_lines = [_clip(desc_text, widths[desc_idx])]
            if plain_prefix and desc_lines and desc_lines[0].startswith(plain_prefix):
                desc_lines[0] = _status_prefix(pkg, color) + desc_lines[0][len(plain_prefix):]
        else:
            desc_lines = None

        n_lines = len(desc_lines) if desc_lines else 1

        for line_no in range(n_lines):
            parts = []
            for i, (col, w) in enumerate(zip(columns, widths, strict=False)):
                cell = row[i] if line_no == 0 else ""
                if i == desc_idx and desc_lines:
                    cell = desc_lines[line_no] if line_no < len(desc_lines) else ""

                if line_no == 0 and i == name_idx:
                    marker_width = 2 if is_installed else 0
                    cell = _clip_name(cell, max(0, w - marker_width))
                    if color:
                        pkg_color = _COLOR_CASK if pkg_type == "cask" else _COLOR_FORMULA
                        marker = (" " + _COLOR_GREEN + "✔" + _RESET) if is_installed else ""
                        styled = _BOLD + pkg_color + cell + _RESET + marker
                    else:
                        marker = " ✔" if is_installed else ""
                        styled = cell + marker
                    pad = w - len(cell) - marker_width
                    parts.append(styled + " " * max(0, pad))
                    continue

                if i != desc_idx:
                    cell = _clip(cell, w)

                if color and line_no == 0 and i == status_idx and cell:
                    if pkg.disabled:
                        parts.append(_COLOR_DISABLED + f"{cell:<{w}}" + _RESET)
                    elif pkg.deprecated:
                        parts.append(_COLOR_DEPRECATED + f"{cell:<{w}}" + _RESET)
                    else:
                        parts.append(f"{cell:<{w}}")
                    continue

                if color and line_no == 0 and col.key == "trending":
                    parts.append(_trend_emphasis(pkg)[1] + f"{cell:>{w}}" + _RESET)
                    continue

                if col.align == "right":
                    parts.append(f"{cell:>{w}}")
                else:
                    parts.append(f"{cell:<{w}}")

            out.write("  ".join(parts).rstrip() + "\n")

    out.write("\n")


def _tsv_cell(value: object) -> str:
    text = "" if value is None else str(value)
    return text.replace("\t", " ").replace("\r", " ").replace("\n", " ")


def render_tsv(
    packages: list[Package],
    columns: list[ColumnDef],
    out: TextIO | None = None,
) -> None:
    if out is None:
        out = sys.stdout
    for pkg in packages:
        cells = []
        for col in columns:
            if col.raw_getter is not None:
                value = col.raw_getter(pkg)
            else:
                value = col.getter(pkg)
            cells.append(_tsv_cell(value))
        out.write("\t".join(cells) + "\n")
