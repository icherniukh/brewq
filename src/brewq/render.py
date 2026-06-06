from __future__ import annotations

import json
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
    headers = [col.header for col in columns]

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
    gaps = 2 * len(columns)  # 2-space padding between columns
    if desc_idx is not None:
        desc_width = max(20, term_width - fixed_width - gaps)
        widths[desc_idx] = desc_width

    # Header
    header_parts = []
    for i, (col, w) in enumerate(zip(columns, widths)):
        if i == desc_idx or col.align == "left":
            header_parts.append(f"{col.header:<{w}}")
        else:
            header_parts.append(f"{col.header:>{w}}")
    separator = "─" * (sum(widths) + gaps)

    out.write("\n")
    if color:
        out.write(_BOLD + "  ".join(header_parts) + _RESET + "\n")
    else:
        out.write("  ".join(header_parts) + "\n")
    out.write(separator + "\n")

    # Rows
    name_idx = next((i for i, c in enumerate(columns) if c.key == "name"), None)
    type_idx = next((i for i, c in enumerate(columns) if c.key == "type"), None)
    installed_idx = next((i for i, c in enumerate(columns) if c.key == "installed"), None)
    status_idx = next((i for i, c in enumerate(columns) if c.key == "status"), None)

    for pkg, row in zip(packages, rows):
        pkg_type = pkg.type
        is_installed = pkg.installed
        pkg_status = pkg.status

        # Wrap description
        if desc_idx is not None:
            desc_lines = _wrap(row[desc_idx], widths[desc_idx])
        else:
            desc_lines = None

        n_lines = len(desc_lines) if desc_lines else 1

        for line_no in range(n_lines):
            parts = []
            for i, (col, w) in enumerate(zip(columns, widths)):
                cell = row[i]
                if i == desc_idx:
                    cell = desc_lines[line_no] if line_no < len(desc_lines) else ""

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


def render_json(
    packages: list[Package],
    columns: list[ColumnDef],
    metric: str = "installs-30d",
    out: TextIO | None = None,
) -> None:
    if out is None:
        out = sys.stdout
    records = []
    for pkg in packages:
        record = {col.key: col.getter(pkg, metric) for col in columns}
        records.append(record)
    json.dump(records, out, indent=2)
    out.write("\n")
