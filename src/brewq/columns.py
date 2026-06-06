from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from brewq.model import Package


@dataclass
class ColumnDef:
    key: str
    header: str
    align: str  # "left" | "right"
    getter: Callable[[Package, str], str]  # (pkg, metric) -> display string


def _installs_str(pkg: Package, metric: str) -> str:
    val = pkg.installs_365d if metric == "installs-365d" else pkg.installs_30d
    if val < 0:
        return "-"
    return f"{val:,}"


_COLUMN_REGISTRY: dict[str, ColumnDef] = {
    "name": ColumnDef("name", "NAME", "left", lambda p, _: p.name),
    "type": ColumnDef("type", "TYPE", "left", lambda p, _: p.type),
    "version": ColumnDef("version", "VERSION", "left", lambda p, _: p.version or "-"),
    "installs": ColumnDef("installs", "INSTALLS", "right", _installs_str),
    "installs_30d": ColumnDef("installs_30d", "30D", "right",
                              lambda p, _: f"{p.installs_30d:,}" if p.installs_30d >= 0 else "-"),
    "installs_90d": ColumnDef("installs_90d", "90D", "right", lambda p, _: "-"),  # not yet fetched
    "installs_365d": ColumnDef("installs_365d", "365D", "right",
                               lambda p, _: f"{p.installs_365d:,}" if p.installs_365d >= 0 else "-"),
    "description": ColumnDef("description", "DESCRIPTION", "left", lambda p, _: p.description or "-"),
    "installed": ColumnDef("installed", "INST", "left",
                           lambda p, _: "✔" if p.installed else ""),
    "status": ColumnDef("status", "STATUS", "left", lambda p, _: p.status),
    "url": ColumnDef("url", "URL", "left", lambda p, _: p.url or "-"),
}

# Canonical aliases
_ALIASES: dict[str, str] = {
    "popularity": "installs",
    "homepage": "url",
}

# Named profiles
_PROFILES: dict[str, list[str]] = {
    "compact": ["name", "installs", "description"],
    "full": ["name", "type", "installs", "installed", "status", "url", "description"],
}
# "default" is driven by config, not hardcoded here


def resolve(spec: str | list[str], default_columns: list[str]) -> list[ColumnDef]:
    """Expand a column spec (profile name or comma-joined key list) into ColumnDef list."""
    if spec == "default":
        keys = default_columns
    elif isinstance(spec, list):
        keys = spec
    elif spec in _PROFILES:
        keys = _PROFILES[spec]
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
