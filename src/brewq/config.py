from __future__ import annotations

import copy
import json
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
    top: int | str


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
        "top": "auto",
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
    "top": ("output", "top"),
    "sort": ("search", "sort"),
    "reverse": ("search", "reverse"),
    "columns": ("output", "columns"),
    "installed-columns": ("list", "columns"),
    "auto-update": ("cache", "auto_refresh"),
    "max-age": ("cache", "max_age_seconds"),
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
        columns.resolve(value, [], allow_auto=section == "output")
    elif section == "search" and key == "sort":
        if not isinstance(value, str):
            raise ValueError("expected a sort field string")
        parse_sort(value)
    elif key in {"reverse", "auto_refresh"}:
        if type(value) is not bool:
            raise ValueError("expected true or false")
    elif key == "top":
        if value != "auto" and (type(value) is not int or value < 0):
            raise ValueError('expected "auto" or a nonnegative integer')
    elif type(value) is not int or value < 0:
        raise ValueError("expected a nonnegative integer")


_REPORTED: set[str] = set()


def _report(message: str) -> None:
    """Print a config diagnostic once per process; several modules load settings."""
    if message not in _REPORTED:
        _REPORTED.add(message)
        print(message, file=sys.stderr)


def validate() -> tuple[Settings, dict[str, str], list[str]]:
    """Read settings with their sources and diagnostics, without printing."""
    cfg = copy.deepcopy(DEFAULTS)
    sources = dict.fromkeys(_SETTINGS, "default")
    diagnostics: list[str] = []
    path = _config_path()
    try:
        with path.open("rb") as fh:
            file_cfg = tomllib.load(fh)
    except FileNotFoundError:
        file_cfg = {}
    except (OSError, ValueError) as exc:
        diagnostics.append(f"brewq: config error ({path}): {exc} — using defaults")
        file_cfg = {}

    def warn(message: str) -> None:
        diagnostics.append(f"brewq: config error ({path}): {message} — using default")

    # Validation is field-local so a typo does not discard neighboring settings.
    sections = cast(dict[str, dict[str, Any]], cfg)
    for name, value in file_cfg.items():
        if name not in _SETTINGS:
            hint = spell.suggestion(name, _SETTINGS)
            warn(f"unknown setting {name!r}" + (f".{hint}" if hint else ""))
            continue
        section, key = _SETTINGS[name]
        try:
            _validate_value(section, key, value)
        except ValueError as exc:
            warn(f"{name}: {exc}")
            continue
        sections[section][key] = value
        sources[name] = "config file"

    return cfg, sources, diagnostics


def load() -> Settings:
    """Load validated settings; invalid file fields retain their built-in default."""
    cfg, _, diagnostics = validate()
    for message in diagnostics:
        _report(message)

    return cfg


def to_toml(cfg: Settings, sources: dict[str, str] | None = None) -> str:
    """Serialize known root keys (strings, integers, booleans and string arrays)."""
    sections = cast(dict[str, dict[str, Any]], cfg)
    return "".join(
        f"{name} = {json.dumps(sections[section][key], ensure_ascii=False)}"
        + (f" # {sources[name]}" if sources is not None else "") + "\n"
        for name, (section, key) in _SETTINGS.items()
    )


def starter_toml() -> str:
    """A new config file: built-in defaults commented out, so it changes nothing."""
    header = ("# brewq configuration. Uncomment a line to override its built-in default;\n"
              "# keys left commented keep following brewq's defaults.\n")
    return header + "".join(f"# {line}\n" for line in to_toml(DEFAULTS).splitlines())


def auto_refresh_enabled(cfg: dict) -> bool:
    """Config enables background updates unless BREWQ_NO_AUTO_REFRESH opts out."""
    raw = os.environ.get("BREWQ_NO_AUTO_REFRESH")
    if raw is not None:
        value = raw.strip().lower()
        if value in {"1", "true", "yes", "on"}:
            return False
        if value not in {"", "0", "false", "no", "off"}:
            _report("brewq: config error: BREWQ_NO_AUTO_REFRESH: expected true or false"
                    " — using configured value")
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
