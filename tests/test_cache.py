from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from brewq import cache as cache_mod
from brewq.model import Package


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Redirect cache dir to a temp dir for every test."""
    monkeypatch.setenv("BREWQ_CACHE_DIR", str(tmp_path))
    yield tmp_path


def _write_cache(tmp_path, data: dict) -> None:
    cache_mod.cache_path().write_text(json.dumps(data))


def test_cache_missing_is_stale():
    assert cache_mod.is_stale(86400) is True


def test_cache_fresh():
    _write_cache(Path(os.environ["BREWQ_CACHE_DIR"]), {"formulae": [], "casks": []})
    assert cache_mod.is_stale(86400) is False


def test_status_missing():
    s = cache_mod.status()
    assert s["exists"] is False
    assert s["formula_count"] == 0


def test_status_present():
    data = {
        "formulae": [{"name": "ripgrep", "full_name": "ripgrep", "installs_30d": 80000}],
        "casks": [],
    }
    _write_cache(Path(os.environ["BREWQ_CACHE_DIR"]), data)
    s = cache_mod.status()
    assert s["exists"] is True
    assert s["formula_count"] == 1
    assert s["has_analytics"] is True


def test_load_packages_empty():
    assert cache_mod.load_packages() == []


def test_load_packages_from_fixture():
    data = {
        "formulae": [
            {
                "name": "ripgrep", "full_name": "ripgrep",
                "desc": "Search tool", "homepage": "https://example.com",
                "versions": {"stable": "15.1.0"}, "installed": [{"version": "15.1.0"}],
                "deprecated": False, "disabled": False, "aliases": ["rg"],
                "installs_30d": 50_000, "installs_365d": 600_000,
            }
        ],
        "casks": [],
    }
    _write_cache(Path(os.environ["BREWQ_CACHE_DIR"]), data)
    pkgs = cache_mod.load_packages()
    assert len(pkgs) == 1
    assert pkgs[0].name == "ripgrep"
    assert pkgs[0].installs_30d == 50_000


def test_clear():
    _write_cache(Path(os.environ["BREWQ_CACHE_DIR"]), {"formulae": [], "casks": []})
    assert cache_mod.cache_path().exists()
    cache_mod.clear()
    assert not cache_mod.cache_path().exists()


def test_refresh_skips_when_fresh():
    _write_cache(Path(os.environ["BREWQ_CACHE_DIR"]), {"formulae": [], "casks": []})
    with patch.object(cache_mod.brew_mod, "info_all") as mock_info:
        cache_mod.refresh(force=False, max_age=86400)
        mock_info.assert_not_called()


def test_refresh_force_calls_brew():
    fake_data = {"formulae": [], "casks": []}
    with patch.object(cache_mod.brew_mod, "info_all", return_value=fake_data), \
         patch.object(cache_mod.analytics_mod, "fetch_all", return_value={}), \
         patch.object(cache_mod.analytics_mod, "merge_into_brew_data", return_value=fake_data):
        cache_mod.refresh(force=True)
    assert cache_mod.cache_path().exists()
