from __future__ import annotations

import copy
import os
import sys
import tomllib
from pathlib import Path
from typing import Any, TypedDict, cast

from brewq import columns
from brewq.options import parse_sort, sort_choices_text


class SearchSettings(TypedDict):
    sort: str


class OutputSettings(TypedDict):
    columns: list[str]
    limit: int


class ListSettings(TypedDict):
    columns: list[str]


class CacheSettings(TypedDict):
    max_age_seconds: int


class Settings(TypedDict):
    search: SearchSettings
    output: OutputSettings
    list: ListSettings
    cache: CacheSettings


DEFAULTS: Settings = {
    "search": {
        "sort": "90d",
    },
    "output": {
        "columns": ["name", "installs_90d", "trending", "description"],
        "limit": 0,
    },
    "list": {
        "columns": ["name", "description"],
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


def _validate_value(section: str, key: str, value: Any) -> None:
    if key == "columns":
        if not isinstance(value, list) or not value or any(
            not isinstance(item, str) for item in value
        ):
            raise ValueError("expected a nonempty array of column names")
        try:
            columns.resolve(value, [], allow_auto=section == "output")
        except ValueError:
            raise ValueError("unknown column name") from None
    elif section == "search" and key == "sort":
        if not isinstance(value, str):
            raise ValueError("expected a sort field string")
        try:
            parse_sort(value)
        except ValueError:
            raise ValueError(f"expected one of: {sort_choices_text()}") from None
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

    # Validation is field-local so one typo does not discard other valid settings.
    sections = cast(dict[str, dict[str, Any]], cfg)
    for section, values in file_cfg.items():
        if section not in sections:
            print(f"brewq: config error ({path}): unknown section {section!r} — ignored",
                  file=sys.stderr)
            continue
        if not isinstance(values, dict):
            print(f"brewq: config error ({path}): {section}: expected a table — using defaults",
                  file=sys.stderr)
            continue
        for key, value in values.items():
            if key not in sections[section]:
                print(f"brewq: config error ({path}): unknown setting {section}.{key} — ignored",
                      file=sys.stderr)
                continue
            try:
                _validate_value(section, key, value)
            except ValueError as exc:
                print(f"brewq: config error ({path}): {section}.{key}: {exc} — using default",
                      file=sys.stderr)
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


def cache_dir() -> Path:
    env = os.environ.get("BREWQ_CACHE_DIR")
    if env:
        return Path(env)
    xdg = os.environ.get("XDG_CACHE_HOME", "")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "brewq"


def config_path() -> Path:
    return _config_path()
