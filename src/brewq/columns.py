from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from brewq.model import Package


@dataclass
class ColumnDef:
    key: str
    header: str
    align: str  # "left" | "right"
    getter: Callable[[Package], str]
    raw_getter: Callable[[Package], object] | None = field(default=None)


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
    "name": ColumnDef("name", "NAME", "left", lambda p: p.name, lambda p: p.name),
    "type": ColumnDef("type", "TYPE", "left", lambda p: p.type, lambda p: p.type),
    "version": ColumnDef("version", "VERSION", "left", _short_version, _version),
    "installs_30d": ColumnDef(
        "installs_30d", "30d", "right",
        lambda p: _fmt(p.installs_30d),
        lambda p: "" if p.installs_30d < 0 else p.installs_30d,
    ),
    "installs_90d": ColumnDef(
        "installs_90d", "90d", "right",
        lambda p: _fmt(p.installs_90d),
        lambda p: "" if p.installs_90d < 0 else p.installs_90d,
    ),
    "installs_365d": ColumnDef(
        "installs_365d", "365d", "right",
        lambda p: _fmt(p.installs_365d),
        lambda p: "" if p.installs_365d < 0 else p.installs_365d,
    ),
    "trending": ColumnDef(
        "trending", "TREND", "right",
        _fmt_trending,
        lambda p: "" if p.trending is None else p.trending,
    ),
    "binaries": ColumnDef(
        "binaries", "BINARIES", "left",
        _fmt_binaries,
        lambda p: "  ".join(p.binaries),
    ),
    "description": ColumnDef(
        "description", "DESCRIPTION", "left",
        lambda p: p.description or "-",
        lambda p: p.description or "",
    ),
    "installed": ColumnDef(
        "installed", "INST", "left",
        lambda p: "✔" if p.installed else "",
        lambda p: "true" if p.installed else "false",
    ),
    "status": ColumnDef("status", "STATUS", "left", lambda p: p.status, lambda p: p.status),
    "url": ColumnDef("url", "URL", "left", lambda p: p.url or "-", lambda p: p.url or ""),
}

CANONICAL_COLUMNS: tuple[str, ...] = tuple(_COLUMN_REGISTRY)

# All aliases resolve to canonical registry keys.
_ALIASES: dict[str, str] = {
    # name
    "n": "name",
    # type
    "t": "type",
    # version
    "v": "version",
    "ver": "version",
    # installs_30d
    "30": "installs_30d",
    "30d": "installs_30d",
    "i30": "installs_30d",
    "installs": "installs_30d",
    # installs_90d
    "90": "installs_90d",
    "90d": "installs_90d",
    "i90": "installs_90d",
    # installs_365d
    "365": "installs_365d",
    "365d": "installs_365d",
    "i365": "installs_365d",
    "y": "installs_365d",
    "year": "installs_365d",
    # trending (recent rate vs own historical baseline)
    "trend": "trending",
    "hot": "trending",
    # binaries
    "bin": "binaries",
    "bins": "binaries",
    # description
    "d": "description",
    "desc": "description",
    # installed
    "i": "installed",
    "inst": "installed",
    # url
    "h": "url",
    "home": "url",
    "homepage": "url",
}

# Column keys shown by -v/--verbose: every useful package field.
FULL_COLUMNS: list[str] = [
    "name", "type", "version", "installed", "status",
    "installs_30d", "installs_90d", "installs_365d", "trending",
    "binaries", "url", "description",
]


def with_url(col_defs: list[ColumnDef]) -> list[ColumnDef]:
    """Return col_defs with the url column added (before description), unless present."""
    if any(c.key == "url" for c in col_defs):
        return col_defs
    url_col = _COLUMN_REGISTRY["url"]
    desc_idx = next((i for i, c in enumerate(col_defs) if c.key == "description"), None)
    if desc_idx is None:
        return [*col_defs, url_col]
    return [*col_defs[:desc_idx], url_col, *col_defs[desc_idx:]]


_RAW_METRIC_KEYS = ("installs_90d", "installs_30d", "installs_365d")


def pick_representative_metric(pkg: Package | None) -> str:
    """Pick whichever raw install-count window has data for the top result, so an
    explicit `auto` column can show one concrete number without exposing all
    three windows. Prefers the standard 90d window, falling back to whichever
    window isn't a -1 (unknown)."""
    if pkg is not None:
        for key in _RAW_METRIC_KEYS:
            if getattr(pkg, key) >= 0:
                return key
    return "installs_90d"


def resolve(
    spec: str | list[str],
    default_columns: list[str],
    representative_metric: str | None = None,
    *,
    allow_auto: bool = True,
) -> list[ColumnDef]:
    """Expand a column spec (comma-joined key list or "default") into ColumnDef list."""
    if spec == "default":
        keys = default_columns
    elif isinstance(spec, list):
        keys = spec
    else:
        keys = [s.strip() for s in spec.split(",")]

    resolved = []
    for key in keys:
        if key == "auto":
            if not allow_auto:
                raise ValueError("Column 'auto' is only available in search configuration")
            canonical = representative_metric or "installs_90d"
        else:
            canonical = _ALIASES.get(key, key)
        col = _COLUMN_REGISTRY.get(canonical)
        if col is None:
            raise ValueError(f"Unknown column {key!r}. Valid: {', '.join(CANONICAL_COLUMNS)}")
        resolved.append(col)
    return resolved
