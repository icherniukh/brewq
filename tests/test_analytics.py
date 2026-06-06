from __future__ import annotations

import json
from pathlib import Path

from brewq.analytics import _parse_count, merge_into_brew_data

FIXTURES = Path(__file__).parent


def test_parse_count_comma_string():
    assert _parse_count("528,018") == 528018


def test_parse_count_int_passthrough():
    assert _parse_count(12345) == 12345


def test_parse_count_invalid():
    assert _parse_count("n/a") == -1


def test_merge_into_brew_data():
    brew_data = json.loads((FIXTURES / "fixtures_brew_info.json").read_text())
    analytics = {
        "formula_30d": {"ripgrep": 80_000, "bat": 50_000},
        "formula_365d": {"ripgrep": 900_000},
        "cask_30d": {},
        "cask_365d": {},
    }
    result = merge_into_brew_data(brew_data, analytics)
    rg = next(f for f in result["formulae"] if f["name"] == "ripgrep")
    assert rg["installs_30d"] == 80_000
    assert rg["installs_365d"] == 900_000

    bat = next(f for f in result["formulae"] if f["name"] == "bat")
    assert bat["installs_30d"] == 50_000
    assert bat["installs_365d"] == -1  # not in analytics fixture


def test_merge_missing_package_gets_minus_one():
    brew_data = {"formulae": [{"name": "unknown-pkg", "full_name": "unknown-pkg"}], "casks": []}
    result = merge_into_brew_data(brew_data, {"formula_30d": {}, "formula_365d": {}, "cask_30d": {}, "cask_365d": {}})
    assert result["formulae"][0]["installs_30d"] == -1
