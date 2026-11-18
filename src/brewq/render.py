from __future__ import annotations

import os
import re
import shutil
import sys
import textwrap
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
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
_NON_ASCII = re.compile(r"[^\x00-\x7f]")
# Control, C1, and bidi-override characters from untrusted package metadata must
# never reach the terminal verbatim (CWE-150): ESC/C1 can inject terminal
# sequences and bidi controls can reorder displayed text. Tab/CR/LF become a
# space (matching TSV); everything else dangerous becomes a visible "?".
_DANGEROUS = re.compile(
    "[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f"
    "\u202a-\u202e\u2066-\u2069\u061c\u200e\u200f\u2028\u2029]"
)


def _sanitize_cell(text: object) -> str:
    cell = "" if text is None else str(text)
    if "\t" in cell or "\r" in cell or "\n" in cell:
        cell = cell.replace("\t", " ").replace("\r", " ").replace("\n", " ")
    return _DANGEROUS.sub("?", cell)


@lru_cache(maxsize=256)
def _trend_emphasis(cell: str) -> tuple[str, str]:
    """Table-only momentum cues; keep the column registry and TSV numeric."""
    value = cell.split(maxsplit=1)[0]
    if value == "-":
        return "", _DIM
    # Reuse the displayed precision instead of recalculating the model's ratio.
    trend = float(value.removesuffix("x"))
    if trend >= 2:
        return "↑↑", _BOLD + _COLOR_GREEN
    if trend >= 1.2:
        return "↑", _COLOR_GREEN
    if trend < 0.8:
        return "↓", _DIM
    return "·", _DIM


def render_cache_note(message: str, out: TextIO, *, no_color: bool = False) -> None:
    """Keep routine cache health visible but subordinate to query results."""
    if _use_color(out, no_color=no_color):
        out.write(_DIM + message + _RESET + "\n")
    else:
        out.write(message + "\n")


def _plain_status_prefix(pkg: Package) -> str:
    if pkg.disabled:
        return "(disabled) "
    if pkg.deprecated:
        return "(deprecated) "
    return ""


def _use_color(out: TextIO, *, no_color: bool = False) -> bool:
    if no_color or os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    return hasattr(out, "isatty") and out.isatty()


def terminal_size() -> os.terminal_size:
    if sys.stdout.isatty():
        try:
            return os.get_terminal_size(sys.stdout.fileno())
        except (OSError, ValueError):
            return os.terminal_size((100, 24))
    return shutil.get_terminal_size((100, 24))


def _terminal_width() -> int:
    return terminal_size().columns


def _display_width(text: str) -> int:
    if text.isascii():
        return len(text)
    return _unicode_width(text)


@lru_cache(maxsize=4096)
def _unicode_width(text: str) -> int:
    return len(text) + sum(
        -1 if unicodedata.combining(char) else
        1 if unicodedata.east_asian_width(char) in {"W", "F"} else 0
        for char in _NON_ASCII.findall(text)
    )


def _take_width(text: str, width: int) -> int:
    """Return the character boundary that fits, including trailing combining marks."""
    used = 0
    for i, char in enumerate(text):
        used += _display_width(char)
        if used > width:
            return i
    return len(text)


def _wrap(text: str, width: int) -> list[str]:
    lines = []
    for line in textwrap.wrap(text, width) or [""]:
        while _display_width(line) > width:
            end = _take_width(line, width)
            # A double-width character cannot fit a one-column terminal.
            lines.append(line[:end] if end else "…")
            line = line[end or 1:]
        if line:
            lines.append(line)
    return lines


def _clip(text: str, width: int) -> str:
    if width <= 0:
        return ""
    if text.isascii():
        return text if len(text) <= width else text[:width - 1].rstrip() + "…"
    if _unicode_width(text) <= width:
        return text
    end = _take_width(text, width - 1)
    return text[:end].rstrip() + "…"


def _clip_name(text: str, width: int) -> str:
    if "/" in text and width >= 3 and _display_width(text) > width:
        prefix, name = text.rsplit("/", 1)
        name_width = _display_width(name)
        if name_width + 2 > width:
            return "…/" + _clip(name, width - 2)
        return _clip(prefix, width - name_width - 1) + "/" + name
    return _clip(text, width)


@lru_cache(maxsize=4096)
def _fit(text: str, width: int, align: str = "left") -> str:
    if text.isascii():
        if len(text) > width:
            text = _clip(text, width)
        return text.rjust(width) if align == "right" else text.ljust(width)
    text = _clip(text, width)
    padding = " " * max(0, width - _display_width(text))
    return padding + text if align == "right" else text + padding


@dataclass
class TableResult:
    hidden: list[str]
    shown: int
    vertical: bool = False


def table_fits(minimums: list[int], term_width: int) -> bool:
    """Report whether the selected cells' readable minimums fit side by side."""
    return sum(minimums) + 2 * max(0, len(minimums) - 1) <= term_width


def _record_lines(
    pkg: Package, columns: list[ColumnDef], headers: list[str], row: list[str],
    term_width: int, show_installed_marker: bool,
) -> list[str]:
    lines = []
    for col, header, cell in zip(columns, headers, row, strict=True):
        if col.key != "name" and cell.strip() in {"", "-"}:
            continue
        if col.key == "name" and pkg.installed and show_installed_marker:
            cell += " ✔"
        lines.extend(_wrap(f"{header}: {cell}", term_width))
    return [*lines, ""]


def render_table(
    packages: list[Package],
    columns: list[ColumnDef],
    out: TextIO | None = None,
    sorted_col: str | None = None,
    *,
    no_color: bool = False,
    installed_only: bool = False,
    auto_height: int | None = None,
    reverse: bool = False,
    named_columns: set[str] | None = None,
) -> TableResult:
    """Render cells and report the shown count and layout for CLI diagnostics."""
    if out is None:
        out = sys.stdout
    color = _use_color(out, no_color=no_color)
    term_width = max(1, _terminal_width())
    show_status_in_description = not any(col.key == "status" for col in columns)
    show_installed_marker = not installed_only and not any(col.key == "inst" for col in columns)
    headers = [col.header + (" ↓" if col.key == sorted_col else "") for col in columns]
    widths = [_display_width(header) for header in headers]

    rows = []
    for pkg in packages:
        row = []
        for i, col in enumerate(columns):
            cell = _sanitize_cell(col.getter(pkg))
            if col.key == "trend" and cell != "-":
                cell += f" {_trend_emphasis(cell)[0]:<2}"
            elif col.key == "url":
                cell = cell.removeprefix("https://")
                address = cell.split("://", 1)[-1]
                if (len(address) > 1 and address.endswith("/") and address.count("/") == 1
                        and "?" not in address and "#" not in address):
                    cell = cell[:-1]
            elif col.key == "desc" and show_status_in_description:
                if prefix := _plain_status_prefix(pkg):
                    cell = (prefix + (cell if cell != "-" else "")).rstrip()
            row.append(cell)
            marker_width = 2 if col.key == "name" and pkg.installed and show_installed_marker else 0
            cell_width = len(cell) if cell.isascii() else _unicode_width(cell)
            widths[i] = max(widths[i], cell_width + marker_width)
        rows.append(row)

    keep = [i for i, col in enumerate(columns)
            if col.key == "name" or any(row[i].strip() not in {"", "-"} for row in rows)]
    hidden = [col.key for i, col in enumerate(columns) if i not in keep]
    if hidden:
        columns = [columns[i] for i in keep]
        rows = [[row[i] for i in keep] for row in rows]
        headers = [headers[i] for i in keep]
        widths = [widths[i] for i in keep]
    if not columns:
        return TableResult(hidden, len(packages))
    desc_idx = next((i for i, col in enumerate(columns) if col.key == "desc"), None)
    name_idx = next((i for i, col in enumerate(columns) if col.key == "name"), None)

    gaps = 2 * (len(columns) - 1)
    minimums = widths.copy()
    for i, col in enumerate(columns):
        if col.key in {"name", "desc", "url", "bin"}:
            minimums[i] = max(_display_width(headers[i]), min(
                8 if col.key == "name" else 20, widths[i],
            ))

    # Preserve short metadata in full; use records when sensible minimums cannot fit.
    if not table_fits(minimums, term_width):
        if auto_height is None:
            blocks = []
            for pkg, row in zip(packages, rows, strict=True):
                lines = _record_lines(pkg, columns, headers, row, term_width, show_installed_marker)
                block = "\n".join(lines[:-1] if lines and lines[-1] == "" else lines)
                if block.strip():
                    blocks.append(block)
            if blocks:
                out.write("\n\n".join(blocks) + "\n")
            return TableResult(hidden, len(blocks), vertical=True)
        # Vertical records include their own separator. Reserve cap/cache notes,
        # the typed command and the next prompt, without table framing blanks.
        named = named_columns or set()
        budget = auto_height - 4 - len(set(hidden) & named)
        candidates = zip(packages, rows, strict=True)
        if reverse:
            candidates = zip(reversed(packages), reversed(rows), strict=True)
        selected = []
        used = 0
        for pkg, row in candidates:
            lines = _record_lines(pkg, columns, headers, row, term_width, show_installed_marker)
            content = lines[:-1] if lines and lines[-1] == "" else lines
            if not any(line.strip() for line in content):
                continue
            if selected:
                extra_notes = sum(
                    col.key in named and row[i].strip() in {"", "-"}
                    and all(previous[i].strip() in {"", "-"} for previous, _ in selected)
                    for i, col in enumerate(columns) if col.key != "name"
                )
                if used + 1 + len(content) + extra_notes > budget:
                    break
                used += 1
            selected.append((row, content))
            used += len(content)
        if reverse:
            selected.reverse()
        hidden.extend(col.key for i, col in enumerate(columns) if col.key != "name"
                      and all(row[i].strip() in {"", "-"} for row, _ in selected))
        blocks = ["\n".join(lines) for _, lines in selected]
        if blocks:
            out.write("\n\n".join(blocks) + "\n")
        return TableResult(hidden, len(blocks), vertical=True)

    # Spend description space first, then long metadata, and clip names last.
    shrink_order = ([desc_idx] if desc_idx is not None else []) + sorted(
        (i for i, col in enumerate(columns) if col.key in {"url", "bin"}),
        key=lambda i: widths[i] - minimums[i], reverse=True,
    ) + ([name_idx] if name_idx is not None else [])
    excess = max(0, sum(widths) + gaps - term_width)
    for i in shrink_order:
        reduction = min(excess, widths[i] - minimums[i])
        widths[i] -= reduction
        excess -= reduction

    header = "  ".join(_fit(text, w, col.align)
                       for text, w, col in zip(headers, widths, columns, strict=True))
    out.write((_BOLD + header + _RESET if color else header) + "\n")
    out.write("─" * (sum(widths) + gaps) + "\n")

    for pkg, row in zip(packages, rows, strict=True):
        parts = []
        for i, (col, w) in enumerate(zip(columns, widths, strict=True)):
            cell = row[i]
            if i == name_idx:
                marker = " ✔" if pkg.installed and show_installed_marker else ""
                cell = _clip_name(cell, w - len(marker))
                cell_width = len(cell) if cell.isascii() else _unicode_width(cell)
                padding = " " * max(0, w - cell_width - len(marker))
                if color:
                    pkg_color = _COLOR_CASK if pkg.type == "cask" else _COLOR_FORMULA
                    cell = _BOLD + pkg_color + cell + _RESET
                    if marker:
                        marker = " " + _COLOR_GREEN + "✔" + _RESET
                parts.append(cell + marker + padding)
                continue

            cell = _fit(cell, w, col.align)
            if color and i == desc_idx and show_status_in_description:
                prefix = _plain_status_prefix(pkg)
                if prefix:
                    status_color = _COLOR_DISABLED if pkg.disabled else _COLOR_DEPRECATED
                    end = min(len(prefix), len(cell.rstrip()))
                    cell = status_color + cell[:end] + _RESET + cell[end:]
            elif color and col.key == "trend":
                cell = _trend_emphasis(row[i])[1] + cell + _RESET
            parts.append(cell)
        out.write("  ".join(parts).rstrip() + "\n")
    return TableResult(hidden, len(packages))


def _tsv_cell(value: object) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\t", " ").replace("\r", " ").replace("\n", " ")
    return _DANGEROUS.sub("?", text)


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
