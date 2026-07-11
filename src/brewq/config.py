from __future__ import annotations

import copy
import os
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]


DEFAULTS: dict[str, Any] = {
    "search": {
        "sort": "90d",
    },
    "output": {
        "columns": ["name", "installs_90d", "trending", "description"],
        "limit": 0,
    },
    "list": {
        "columns": ["name", "type", "version", "description"],
    },
    "cache": {
        "max_age_seconds": 86400,
    },
    "presets": {},
}


def _config_path() -> Path:
    env = os.environ.get("BREWQ_CONFIG")
    if env:
        return Path(env)
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "brewq" / "config.toml"


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load() -> dict[str, Any]:
    cfg = copy.deepcopy(DEFAULTS)
    path = _config_path()
    if path.exists():
        try:
            with path.open("rb") as fh:
                file_cfg = tomllib.load(fh)
            cfg = _deep_merge(cfg, file_cfg)
        except Exception as exc:
            print(
                f"brewq: config error ({path}): {exc} — using defaults",
                file=sys.stderr,
            )

    # Environment overrides
    if os.environ.get("BREWQ_CACHE_MAX_AGE"):
        cfg["cache"]["max_age_seconds"] = int(os.environ["BREWQ_CACHE_MAX_AGE"])

    return cfg


def cache_dir() -> Path:
    env = os.environ.get("BREWQ_CACHE_DIR")
    if env:
        return Path(env)
    xdg = os.environ.get("XDG_CACHE_HOME", "")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "brewq"


def config_path() -> Path:
    return _config_path()


_SECTION_ORDER = ("search", "output", "list", "cache", "presets")


def _serialize_value(val: Any) -> str:
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, int):
        return str(val)
    if isinstance(val, str):
        return f'"{val}"'
    if isinstance(val, list):
        return "[" + ", ".join(f'"{v}"' for v in val) + "]"
    raise TypeError(f"Cannot serialize {type(val).__name__} to TOML")


def _serialize_toml(cfg: dict[str, Any]) -> str:
    lines: list[str] = []
    ordered = list(_SECTION_ORDER)
    for key in cfg:
        if key not in _SECTION_ORDER:
            ordered.append(key)
    for section in ordered:
        if section not in cfg:
            continue
        data = cfg[section]
        if not isinstance(data, dict) or not data:
            continue
        lines.append(f"[{section}]")
        for k, v in data.items():
            lines.append(f"{k} = {_serialize_value(v)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def save(cfg: dict[str, Any]) -> None:
    """Write config dict back to config.toml."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_serialize_toml(cfg), encoding="utf-8")
