from __future__ import annotations

import copy
import os
import sys
import tomllib
from pathlib import Path
from typing import Any, TypedDict, cast

from brewq import columns, spell
from brewq.options import parse_sort


class SearchSettings(TypedDict):
    sort: str
    reverse: bool


class OutputSettings(TypedDict):
    columns: list[str]
    limit: int


class ListSettings(TypedDict):
    columns: list[str]


class CacheSettings(TypedDict):
    max_age_seconds: int
    auto_refresh: bool


class Settings(TypedDict):
    search: SearchSettings
    output: OutputSettings
    list: ListSettings
    cache: CacheSettings


DEFAULTS: Settings = {
    "search": {
        "sort": "90d",
        "reverse": False,
    },
    "output": {
        "columns": ["name", "90d", "trend", "desc"],
        "limit": 0,
    },
    "list": {
        "columns": ["name", "desc"],
    },
    "cache": {
        "max_age_seconds": 86400,
        "auto_refresh": True,
    },
}


# Root TOML keys match long option spellings; internal settings retain their owners.
_SETTINGS = {
    "top": ("output", "limit"),
    "sort": ("search", "sort"),
    "reverse": ("search", "reverse"),
    "columns": ("output", "columns"),
    "installed-columns": ("list", "columns"),
    "auto-update": ("cache", "auto_refresh"),
    "max-age": ("cache", "max_age_seconds"),
}
_OLD_SETTINGS = {f"{section}.{key}": name for name, (section, key) in _SETTINGS.items()}
_OLD_SETTINGS.update({"limit": "top", "auto_refresh": "auto-update", "max_age_seconds": "max-age"})


def _config_path() -> Path:
    env = os.environ.get("BREWQ_CONFIG")
    if env:
        return Path(env)
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "brewq" / "config.toml"


def _validate_value(section: str, key: str, value: Any) -> None:
    if key == "columns":
        if not isinstance(value, list) or not value or any(
            not isinstance(item, str) for item in value
        ):
            raise ValueError("expected a nonempty array of column names")
        columns.resolve(value, [], allow_auto=section == "output")
    elif section == "search" and key == "sort":
        if not isinstance(value, str):
            raise ValueError("expected a sort field string")
        parse_sort(value)
    elif key in {"reverse", "auto_refresh"}:
        if type(value) is not bool:
            raise ValueError("expected true or false")
    elif type(value) is not int or value < 0:
        raise ValueError("expected a nonnegative integer")


def load() -> Settings:
    """Load validated settings; invalid file fields retain their built-in default."""
    cfg = copy.deepcopy(DEFAULTS)
    path = _config_path()
    try:
        with path.open("rb") as fh:
            file_cfg = tomllib.load(fh)
    except FileNotFoundError:
        file_cfg = {}
    except (OSError, ValueError) as exc:
        print(f"brewq: config error ({path}): {exc} — using defaults", file=sys.stderr)
        file_cfg = {}

    def warn(message: str) -> None:
        print(f"brewq: config error ({path}): {message} — using default", file=sys.stderr)

    # Validation is field-local so a typo does not discard neighboring settings.
    sections = cast(dict[str, dict[str, Any]], cfg)
    for name, value in file_cfg.items():
        if name not in _SETTINGS:
            if name in cfg and isinstance(value, dict) and value:
                for key in value:
                    old = f"{name}.{key}"
                    replacement = _OLD_SETTINGS.get(old)
                    if replacement:
                        warn(f"{old} was removed; use root key {replacement!r}")
                    else:
                        warn(f"unknown setting {old!r}.{spell.suggestion(key, _SETTINGS)}")
            elif name in _OLD_SETTINGS:
                warn(f"{name} was removed; use {_OLD_SETTINGS[name]!r}")
            else:
                replacements = [new for new, (section, _) in _SETTINGS.items() if section == name]
                hint = (f" Use root keys: {', '.join(replacements)}." if replacements
                        else spell.suggestion(name, _SETTINGS))
                warn(f"unknown setting {name!r}.{hint}")
            continue
        section, key = _SETTINGS[name]
        try:
            _validate_value(section, key, value)
        except ValueError as exc:
            warn(f"{name}: {exc}")
            continue
        sections[section][key] = value

    # An invalid environment override leaves the validated file/default value intact.
    raw_age = os.environ.get("BREWQ_CACHE_MAX_AGE")
    if raw_age is not None:
        try:
            age = int(raw_age)
            _validate_value("cache", "max_age_seconds", age)
        except ValueError:
            print("brewq: config error: BREWQ_CACHE_MAX_AGE: expected a nonnegative integer"
                  " — using configured value", file=sys.stderr)
        else:
            cfg["cache"]["max_age_seconds"] = age

    return cfg


def auto_refresh_enabled(cfg: dict) -> bool:
    """Config enables background updates unless BREWQ_NO_AUTO_REFRESH opts out."""
    raw = os.environ.get("BREWQ_NO_AUTO_REFRESH")
    if raw is not None:
        value = raw.strip().lower()
        if value in {"1", "true", "yes", "on"}:
            return False
        if value not in {"", "0", "false", "no", "off"}:
            print("brewq: config error: BREWQ_NO_AUTO_REFRESH: expected true or false"
                  " — using configured value", file=sys.stderr)
    return bool(cfg["cache"]["auto_refresh"])


def cache_dir() -> Path:
    env = os.environ.get("BREWQ_CACHE_DIR")
    if env:
        return Path(env)
    xdg = os.environ.get("XDG_CACHE_HOME", "")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "brewq"


def config_path() -> Path:
    return _config_path()
