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


def _fmt_popularity(p: Package) -> str:
    s = p.popularity_score
    return "-" if s < 0 else str(s)


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
    "popularity": ColumnDef(
        "popularity", "POP", "right",
        _fmt_popularity,
        lambda p: "" if p.popularity_score < 0 else p.popularity_score,
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
    # popularity (composite score)
    "pop": "popularity",
    "score": "popularity",
    "rank": "popularity",
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
    "compact": ["name", "installs_30d", "description"],
    "full": ["name", "type", "version", "installs_30d", "installs_90d", "installs_365d", "installed", "status", "description"],
}
# Named profiles for installed-package output.
_LIST_PROFILES: dict[str, list[str]] = {
    "compact": ["name", "type", "description"],
    "full": ["name", "type", "version", "installs_30d", "installed", "status", "description"],
}
# "default" is driven by config, not hardcoded here


def resolve(
    spec: str | list[str],
    default_columns: list[str],
    profiles: dict[str, list[str]] | None = None,
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
        canonical = _ALIASES.get(key, key)
        col = _COLUMN_REGISTRY.get(canonical)
        if col is None:
            valid = sorted(set(list(_COLUMN_REGISTRY) + list(_ALIASES)))
            raise ValueError(f"Unknown column {key!r}. Valid: {', '.join(valid)}")
        resolved.append(col)
    return resolved


def available_keys() -> list[str]:
    return sorted(set(list(_COLUMN_REGISTRY) + list(_ALIASES)))


def list_profiles() -> dict[str, list[str]]:
    return dict(_LIST_PROFILES)


def search_profiles() -> dict[str, list[str]]:
    return dict(_SEARCH_PROFILES)
