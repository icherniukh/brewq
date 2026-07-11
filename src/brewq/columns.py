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
    version = pkg.version or "-"
    max_len = 20
    if len(version) <= max_len:
        return version
    prefix_len = 10
    suffix_len = 8
    return f"{version[:prefix_len]}…{version[-suffix_len:]}"


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
    "version": ColumnDef("version", "VERSION", "left", _short_version, lambda p: p.version or ""),
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
    "pop": "trending",
    "popularity": "trending",
    "score": "trending",
    "rank": "trending",
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

# Named profiles for search output.
_SEARCH_PROFILES: dict[str, list[str]] = {
    "compact": ["name", "installs_90d", "description"],
    "full": ["name", "type", "version", "installs_30d", "installs_90d", "installs_365d", "installed", "status", "description"],
}
# Named profiles for installed-package output.
_LIST_PROFILES: dict[str, list[str]] = {
    "compact": ["name", "type", "description"],
    "full": ["name", "type", "version", "installs_90d", "installed", "status", "description"],
}
# "default" is driven by config, not hardcoded here


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
    profiles: dict[str, list[str]] | None = None,
    representative_metric: str | None = None,
) -> list[ColumnDef]:
    """Expand a column spec (profile name or comma-joined key list) into ColumnDef list."""
    if profiles is None:
        profiles = _SEARCH_PROFILES
    if spec == "default":
        keys = default_columns
    elif isinstance(spec, list):
        keys = spec
    elif spec in profiles:
        keys = profiles[spec]
    else:
        keys = [s.strip() for s in spec.split(",")]

    resolved = []
    for key in keys:
        if key == "auto":
            canonical = representative_metric or "installs_90d"
        else:
            canonical = _ALIASES.get(key, key)
        col = _COLUMN_REGISTRY.get(canonical)
        if col is None:
            valid = sorted(set(list(_COLUMN_REGISTRY) + list(_ALIASES)))
            raise ValueError(f"Unknown column {key!r}. Valid: {', '.join(valid)}")
        resolved.append(col)
    return resolved


def list_profiles() -> dict[str, list[str]]:
    return dict(_LIST_PROFILES)
