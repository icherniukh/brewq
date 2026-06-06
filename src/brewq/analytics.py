from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Any

_URLS = {
    "formula_30d": "https://formulae.brew.sh/api/analytics/install/30d.json",
    "formula_365d": "https://formulae.brew.sh/api/analytics/install/365d.json",
    "cask_30d": "https://formulae.brew.sh/api/analytics/cask-install/30d.json",
    "cask_365d": "https://formulae.brew.sh/api/analytics/cask-install/365d.json",
}

_TIMEOUT = 15


def _fetch(url: str) -> list[dict]:
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read())["items"]
    except (urllib.error.URLError, KeyError, json.JSONDecodeError):
        return []


def fetch_all() -> dict[str, dict[str, int]]:
    """Fetch all four analytics feeds. Returns nested dict: {key: {name: count}}."""
    result: dict[str, dict[str, int]] = {}
    for key, url in _URLS.items():
        items = _fetch(url)
        if "formula" in key:
            result[key] = {
                item["formula"]: _parse_count(item["count"])
                for item in items
                if "formula" in item
            }
        else:
            result[key] = {
                item["cask"]: _parse_count(item["count"])
                for item in items
                if "cask" in item
            }
    return result


def _parse_count(value: str | int) -> int:
    if isinstance(value, int):
        return value
    try:
        return int(str(value).replace(",", ""))
    except ValueError:
        return -1


def merge_into_brew_data(
    brew_data: dict[str, Any],
    analytics: dict[str, dict[str, int]],
) -> dict[str, Any]:
    """Annotate brew_data formulae/casks with analytics counts in-place."""
    f30 = analytics.get("formula_30d", {})
    f365 = analytics.get("formula_365d", {})
    c30 = analytics.get("cask_30d", {})
    c365 = analytics.get("cask_365d", {})

    for formula in brew_data.get("formulae", []):
        name = formula.get("full_name") or formula.get("name", "")
        formula["installs_30d"] = f30.get(name, -1)
        formula["installs_365d"] = f365.get(name, -1)

    for cask in brew_data.get("casks", []):
        token = cask.get("token", "")
        cask["installs_30d"] = c30.get(token, -1)
        cask["installs_365d"] = c365.get(token, -1)

    return brew_data
