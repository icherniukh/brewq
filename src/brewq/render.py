from __future__ import annotations

import os
import shutil
import sys
import textwrap
from typing import TextIO

from brewq.columns import ColumnDef
from brewq.model import Package

# ANSI escape sequences
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"
_COLOR_FORMULA = "\033[38;5;183m"   # lavender
_COLOR_CASK = "\033[38;5;115m"      # seafoam green
_COLOR_GREEN = "\033[32m"
_COLOR_DEPRECATED = "\033[38;5;208m"  # orange
_COLOR_DISABLED = "\033[38;5;167m"    # red


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


def _header(col: ColumnDef, metric: str) -> str:
    if col.key == "installs":
        return "INSTALLS(365d)" if metric == "installs-365d" else "INSTALLS(30d)"
    return col.header


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
    metric: str = "installs-30d",
    out: TextIO | None = None,
) -> None:
    if out is None:
        out = sys.stdout
    color = _use_color(out)
    term_width = _terminal_width()

    # Compute raw cell values
    rows: list[list[str]] = [
        [col.getter(pkg, metric) for col in columns]
        for pkg in packages
    ]
    headers = [_header(col, metric) for col in columns]

    # Find description column index (wrappable)
    desc_idx = next(
        (i for i, col in enumerate(columns) if col.key == "description"),
        None,
    )

    # Compute column widths from content (header or data)
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i != desc_idx:
                widths[i] = max(widths[i], len(cell))

    # Cap description width to fill terminal
    fixed_width = sum(widths[i] for i in range(len(columns)) if i != desc_idx)
    gaps = 2 * max(0, len(columns) - 1)  # 2-space padding between columns
    if desc_idx is not None:
        desc_width = max(20, term_width - fixed_width - gaps)
        widths[desc_idx] = desc_width

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
    name_idx = next((i for i, c in enumerate(columns) if c.key == "name"), None)
    desc_idx_for_status = next((i for i, c in enumerate(columns) if c.key == "description"), None)
    status_idx = next((i for i, c in enumerate(columns) if c.key == "status"), None)

    for pkg, row in zip(packages, rows, strict=False):
        pkg_type = pkg.type
        is_installed = pkg.installed

        # Wrap description. Status prefixes are part of the visible description
        # cell, so include them before wrapping instead of prepending afterward.
        if desc_idx is not None:
            desc_text = _plain_status_prefix(pkg) + row[desc_idx]
            desc_lines = _wrap(desc_text, widths[desc_idx])
        else:
            desc_lines = None

        n_lines = len(desc_lines) if desc_lines else 1

        for line_no in range(n_lines):
            parts = []
            for i, (col, w) in enumerate(zip(columns, widths, strict=False)):
                cell = row[i]
                if i == desc_idx:
                    cell = desc_lines[line_no] if line_no < len(desc_lines) else ""
                    if line_no == 0 and i == desc_idx_for_status:
                        plain_prefix = _plain_status_prefix(pkg)
                        if plain_prefix and cell.startswith(plain_prefix):
                            cell = _status_prefix(pkg, color) + cell[len(plain_prefix):]

                if line_no > 0 and i != desc_idx:
                    # continuation lines: only desc column has content
                    cell = ""

                if color and line_no == 0:
                    if i == name_idx:
                        pkg_color = _COLOR_CASK if pkg_type == "cask" else _COLOR_FORMULA
                        marker = (" " + _COLOR_GREEN + "✔" + _RESET) if is_installed else ""
                        # Bold for installed
                        styled = _BOLD + pkg_color + cell + _RESET + marker
                        # Pad without ANSI codes affecting width
                        pad = w - len(cell) - (2 if is_installed else 0)
                        parts.append(styled + " " * max(0, pad))
                        continue
                    elif i == status_idx and cell:
                        if cell == "disabled":
                            parts.append(_COLOR_DISABLED + f"{cell:<{w}}" + _RESET)
                        elif cell == "deprecated":
                            parts.append(_COLOR_DEPRECATED + f"{cell:<{w}}" + _RESET)
                        else:
                            parts.append(f"{cell:<{w}}")
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
    metric: str = "installs-30d",
    out: TextIO | None = None,
) -> None:
    if out is None:
        out = sys.stdout
    for pkg in packages:
        cells = []
        for col in columns:
            if col.raw_getter is not None:
                value = col.raw_getter(pkg, metric)
            else:
                value = col.getter(pkg, metric)
            cells.append(_tsv_cell(value))
        out.write("\t".join(cells) + "\n")
