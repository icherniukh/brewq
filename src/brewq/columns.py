from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from brewq import spell
from brewq.model import Package


@dataclass
class ColumnDef:
    key: str
    header: str
    align: str  # "left" | "right"
    getter: Callable[[Package], str]
    raw_getter: Callable[[Package], object] | None = field(default=None)
    description: str = ""


def _short_version(pkg: Package) -> str:
    version = _version(pkg) or "-"
    max_len = 20
    if len(version) <= max_len:
        return version
    prefix_len = 10
    suffix_len = 8
    return f"{version[:prefix_len]}…{version[-suffix_len:]}"


def _version(pkg: Package) -> str:
    return pkg.installed_version if pkg.installed and pkg.installed_version else pkg.version


def _fmt(val: int) -> str:
    return "-" if val < 0 else f"{val:,}"


def _fmt_trending(p: Package) -> str:
    t = p.trending
    if t is None:
        return "-"
    return f"{t:.1f}x"


def _fmt_binaries(p: Package) -> str:
    return "  ".join(p.binaries) if p.binaries else "-"


_COLUMN_REGISTRY: dict[str, ColumnDef] = {
    "name": ColumnDef(
        "name", "NAME", "left", lambda p: p.name, lambda p: p.name,
        description="package name",
    ),
    "type": ColumnDef(
        "type", "TYPE", "left", lambda p: p.type, lambda p: p.type,
        description="formula or cask",
    ),
    "ver": ColumnDef(
        "ver", "VER", "left", _short_version, _version,
        description="installed version when present; otherwise catalog version",
    ),
    "30d": ColumnDef(
        "30d", "30d", "right",
        lambda p: _fmt(p.installs_30d),
        lambda p: "" if p.installs_30d < 0 else p.installs_30d,
        description="installs in the last 30 days",
    ),
    "90d": ColumnDef(
        "90d", "90d", "right",
        lambda p: _fmt(p.installs_90d),
        lambda p: "" if p.installs_90d < 0 else p.installs_90d,
        description="installs in the last 90 days",
    ),
    "365d": ColumnDef(
        "365d", "365d", "right",
        lambda p: _fmt(p.installs_365d),
        lambda p: "" if p.installs_365d < 0 else p.installs_365d,
        description="installs in the last 365 days",
    ),
    "trend": ColumnDef(
        "trend", "TREND", "right",
        _fmt_trending,
        lambda p: "" if p.trending is None else p.trending,
        description="recent rate relative to the package's earlier rate",
    ),
    "bin": ColumnDef(
        "bin", "BIN", "left",
        _fmt_binaries,
        lambda p: "  ".join(p.binaries),
        description="installed executable names, when known",
    ),
    "url": ColumnDef(
        "url", "URL", "left", lambda p: p.url or "-", lambda p: p.url or "",
        description="homepage URL",
    ),
    "desc": ColumnDef(
        "desc", "DESC", "left",
        lambda p: p.description or "-",
        lambda p: p.description or "",
        description="package description",
    ),
    "inst": ColumnDef(
        "inst", "INST", "left",
        lambda p: "✔" if p.installed else "",
        lambda p: "true" if p.installed else "false",
        description="whether the package is installed",
    ),
    "status": ColumnDef(
        "status", "STATUS", "left", lambda p: p.status, lambda p: p.status,
        description="deprecated or disabled state",
    ),
}

CANONICAL_COLUMNS: tuple[str, ...] = tuple(_COLUMN_REGISTRY)


def reference_lines() -> tuple[str, ...]:
    """Return the canonical column reference for CLI documentation."""
    width = max(len(key) for key in CANONICAL_COLUMNS) + 2
    return tuple(
        f"  {key:<{width}}{column.description}"
        for key, column in _COLUMN_REGISTRY.items()
    )


def selection_help() -> str:
    """Discover fields and the exact-list grammar from the shared registry."""
    return "\n".join([
        "Output fields (use -c with search or +list):", "", *reference_lines(),
        "", "  inst and status are TSV-only; tables use the name marker and desc prefix.",
        "  -c name,ver,90d      select fields in this order",
        "  -c default,url       append URL to the configured view",
        "  -c url,default       put URL first, then the configured view",
        "  -c all               every field available in the output mode",
        "  -c default           use the configured view",
        "", "Duplicates keep their first occurrence. +x/-x edits are no longer supported.",
        "default and all may change between releases; scripts should list fields.",
    ]) + "\n"


# Migration diagnostics only: these spellings are never accepted or resolved.
REMOVED_NAMES: dict[str, str] = {
    "n": "name", "t": "type", "v": "ver", "version": "ver",
    "30": "30d", "i30": "30d", "installs": "30d", "installs_30d": "30d",
    "90": "90d", "i90": "90d", "installs_90d": "90d",
    "365": "365d", "i365": "365d", "y": "365d", "year": "365d",
    "installs_365d": "365d", "trending": "trend", "hot": "trend",
    "binaries": "bin", "bins": "bin", "description": "desc", "d": "desc",
    "installed": "inst", "i": "inst", "h": "url", "home": "url", "homepage": "url",
}
TSV_ONLY = frozenset({"inst", "status"})


# Column keys shown by -c all: every useful package field.
FULL_COLUMNS: list[str] = [
    "name", "type", "ver", "inst", "status",
    "30d", "90d", "365d", "trend",
    "bin", "url", "desc",
]


_RAW_METRIC_KEYS = ("90d", "30d", "365d")


def pick_representative_metric(pkg: Package | None) -> str:
    """Pick whichever raw install-count window has data for the top result, so an
    explicit `auto` column can show one concrete number without exposing all
    three windows. Prefers the standard 90d window, falling back to whichever
    window isn't a -1 (unknown)."""
    if pkg is not None:
        for key in _RAW_METRIC_KEYS:
            if getattr(pkg, f"installs_{key}") >= 0:
                return key
    return "90d"


def resolve(
    spec: str | list[str],
    default_columns: list[str],
    representative_metric: str | None = None,
    *,
    allow_auto: bool = True,
) -> list[ColumnDef]:
    """Resolve exact field names; auto remains a configuration-only pseudo-column."""
    keys = default_columns if spec == "default" else (
        spec if isinstance(spec, list) else [s.strip() for s in spec.split(",")]
    )
    resolved = []
    for key in keys:
        if key == "auto":
            if not allow_auto:
                raise ValueError("Column 'auto' is only available in search configuration")
            key = representative_metric or "90d"
        col = _COLUMN_REGISTRY.get(key)
        if col is None:
            if key in REMOVED_NAMES:
                raise ValueError(f"Column {key!r} was removed; use {REMOVED_NAMES[key]!r}")
            raise ValueError(
                f"Unknown column {key!r}.{spell.suggestion(key, CANONICAL_COLUMNS)} "
                f"Valid: {', '.join(CANONICAL_COLUMNS)}. Use '-c help' for fields and examples."
            )
        if col not in resolved:
            resolved.append(col)
    return resolved


def select(
    spec: str | list[str],
    default_columns: list[str],
    representative_metric: str | None = None,
    *,
    tsv: bool = False,
) -> list[ColumnDef]:
    """Expand ordered lists and reserved words, keeping the first occurrence."""
    tokens = spec if isinstance(spec, list) else [token.strip() for token in spec.split(",")]
    if any(token.startswith(("+", "-")) for token in tokens):
        # Reproduce the retired edits only to print a concrete migration command.
        selected = resolve(default_columns, [], representative_metric)
        operation = "+"
        for token in tokens:
            if token.startswith(("+", "-")):
                operation, token = token[0], token[1:].strip()
            col = resolve(REMOVED_NAMES.get(token, token), [], allow_auto=False)[0]
            if operation == "-":
                selected = [existing for existing in selected if existing.key != col.key]
            elif col not in selected:
                desc_idx = next((i for i, item in enumerate(selected) if item.key == "desc"),
                                len(selected))
                selected.insert(desc_idx, col)
        equivalent = ",".join(col.key for col in selected)
        guidance = f"use -c {equivalent}" if equivalent else "select at least one field with -c"
        raise ValueError(f"Column +x/-x edits were removed; {guidance}")

    selected = []
    for token in tokens:
        if token == "default":
            expanded = resolve(default_columns, [], representative_metric)
        elif token == "all":
            expanded = resolve([key for key in FULL_COLUMNS if tsv or key not in TSV_ONLY], [])
        elif not token:
            raise ValueError("Empty column name in -c; separate fields with single commas.")
        else:
            expanded = resolve(token, [], allow_auto=False)
        for col in expanded:
            if not tsv and col.key in TSV_ONLY:
                shown = ("as the ✔ after the name" if col.key == "inst"
                         else "as the desc prefix")
                raise ValueError(f"Column {col.key!r} is TSV-only; use --tsv -c {col.key}. "
                                 f"Tables show it {shown}.")
            if col not in selected:
                selected.append(col)
    if not selected:
        raise ValueError("Column selection must keep at least one field. Use '-c help' for fields.")
    return selected
