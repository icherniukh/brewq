from __future__ import annotations

import json
from typing import Any

# Formulae use install_on_request (excludes dependency drag).
# Casks are always explicitly requested, so regular cask-install ≈ on-request.
_URLS = {
    "formula_30d":  "https://formulae.brew.sh/api/analytics/install-on-request/30d.json",
    "formula_90d":  "https://formulae.brew.sh/api/analytics/install-on-request/90d.json",
    "formula_365d": "https://formulae.brew.sh/api/analytics/install-on-request/365d.json",
    "cask_30d":     "https://formulae.brew.sh/api/analytics/cask-install/30d.json",
    "cask_90d":     "https://formulae.brew.sh/api/analytics/cask-install/90d.json",
    "cask_365d":    "https://formulae.brew.sh/api/analytics/cask-install/365d.json",
}

_TIMEOUT = 15


class AnalyticsFetchError(RuntimeError):
    """One analytics feed could not be retrieved or decoded."""

    def __init__(self, feed: str, detail: str):
        super().__init__(f"{feed}: {detail}")
        self.feed = feed
        self.detail = detail


def _fetch(feed: str, url: str) -> list[dict]:
    # Imported here: only refreshes touch the network, and urllib is slow to import.
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT) as resp:
            payload = json.loads(resp.read())
        items = payload["items"]
        if not isinstance(items, list):
            raise TypeError("items is not a list")
        return items
    except urllib.error.URLError as exc:
        raise AnalyticsFetchError(feed, str(exc.reason)) from exc
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise AnalyticsFetchError(feed, f"invalid response: {exc}") from exc


def fetch_all() -> dict[str, dict[str, int]]:
    """Fetch all six analytics feeds. Returns nested dict: {key: {name: count}}."""
    result: dict[str, dict[str, int]] = {}
    for key, url in _URLS.items():
        items = _fetch(key, url)
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
    f30  = analytics.get("formula_30d", {})
    f90  = analytics.get("formula_90d", {})
    f365 = analytics.get("formula_365d", {})
    c30  = analytics.get("cask_30d", {})
    c90  = analytics.get("cask_90d", {})
    c365 = analytics.get("cask_365d", {})

    for formula in brew_data.get("formulae", []):
        name = formula.get("full_name") or formula.get("name", "")
        formula["installs_30d"]  = f30.get(name, -1)
        formula["installs_90d"]  = f90.get(name, -1)
        formula["installs_365d"] = f365.get(name, -1)

    for cask in brew_data.get("casks", []):
        token = cask.get("token", "")
        cask["installs_30d"]  = c30.get(token, -1)
        cask["installs_90d"]  = c90.get(token, -1)
        cask["installs_365d"] = c365.get(token, -1)

    return brew_data
