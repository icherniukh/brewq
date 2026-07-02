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
        "sort": "trending",
    },
    "output": {
        "columns": ["name", "trending", "auto", "description"],
        "limit": 0,
    },
    "list": {
        "columns": ["name", "type", "version", "description"],
    },
    "cache": {
        "max_age_seconds": 86400,
    },
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
