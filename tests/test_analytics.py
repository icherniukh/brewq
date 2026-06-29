from __future__ import annotations

import json
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

from brewq.analytics import (
    AnalyticsFetchError,
    _fetch,
    _parse_count,
    fetch_all,
    merge_into_brew_data,
)

FIXTURES = Path(__file__).parent


def test_parse_count_comma_string():
    assert _parse_count("528,018") == 528018


def test_parse_count_int_passthrough():
    assert _parse_count(12345) == 12345


def test_parse_count_invalid():
    assert _parse_count("n/a") == -1


def test_fetch_names_transport_failure():
    with patch(
        "brewq.analytics.urllib.request.urlopen",
        side_effect=urllib.error.URLError("offline"),
    ), pytest.raises(AnalyticsFetchError, match="formula_30d: offline"):
        _fetch("formula_30d", "https://example.test/analytics.json")


def test_fetch_all_stops_on_failed_feed():
    with patch(
        "brewq.analytics._fetch",
        side_effect=AnalyticsFetchError("formula_30d", "offline"),
    ), pytest.raises(AnalyticsFetchError) as exc:
        fetch_all()

    assert exc.value.feed == "formula_30d"


def test_merge_into_brew_data():
    brew_data = json.loads((FIXTURES / "fixtures_brew_info.json").read_text())
    analytics = {
        "formula_30d":  {"ripgrep": 80_000, "bat": 50_000},
        "formula_90d":  {"ripgrep": 240_000},
        "formula_365d": {"ripgrep": 900_000},
        "cask_30d":  {},
        "cask_90d":  {},
        "cask_365d": {},
    }
    result = merge_into_brew_data(brew_data, analytics)
    rg = next(f for f in result["formulae"] if f["name"] == "ripgrep")
    assert rg["installs_30d"] == 80_000
    assert rg["installs_90d"] == 240_000
    assert rg["installs_365d"] == 900_000

    bat = next(f for f in result["formulae"] if f["name"] == "bat")
    assert bat["installs_30d"] == 50_000
    assert bat["installs_90d"] == -1   # not in analytics fixture
    assert bat["installs_365d"] == -1


def test_merge_missing_package_gets_minus_one():
    brew_data = {"formulae": [{"name": "unknown-pkg", "full_name": "unknown-pkg"}], "casks": []}
    empty = {"formula_30d": {}, "formula_90d": {}, "formula_365d": {},
             "cask_30d": {}, "cask_90d": {}, "cask_365d": {}}
    result = merge_into_brew_data(brew_data, empty)
    assert result["formulae"][0]["installs_30d"] == -1
    assert result["formulae"][0]["installs_90d"] == -1
