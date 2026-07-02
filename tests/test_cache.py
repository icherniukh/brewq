from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from brewq import cache as cache_mod


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


def test_load_computes_age_from_real_file_mtime():
    """cache.load() derives age_seconds from the cache file's real mtime.

    Every other cache-age test injects age_seconds directly via a mocked
    CacheLoad, so none of them exercise this file-timestamp arithmetic.
    """
    data = {"formulae": [{"name": "ripgrep", "full_name": "ripgrep", "desc": "",
                           "homepage": "", "versions": {"stable": "1.0"},
                           "deprecated": False, "disabled": False, "aliases": []}],
            "casks": []}
    _write_cache(Path(os.environ["BREWQ_CACHE_DIR"]), data)
    stamp = cache_mod.cache_path().stat().st_mtime - 90
    os.utime(cache_mod.cache_path(), (stamp, stamp))

    loaded = cache_mod.load()

    assert loaded.source == "user"
    assert 89 <= loaded.age_seconds <= 91


def test_clear():
    _write_cache(Path(os.environ["BREWQ_CACHE_DIR"]), {"formulae": [], "casks": []})
    assert cache_mod.cache_path().exists()
    cache_mod.clear()
    assert not cache_mod.cache_path().exists()


def test_refresh_skips_when_fresh():
    _write_cache(Path(os.environ["BREWQ_CACHE_DIR"]), {"formulae": [], "casks": []})
    with patch.object(cache_mod.brew_mod, "info_all") as mock_info:
        result = cache_mod.refresh(force=False, max_age=86400)
        mock_info.assert_not_called()
    assert result.outcome is cache_mod.RefreshOutcome.FRESH


def test_refresh_force_calls_brew():
    fake_data = {"formulae": [], "casks": []}
    with patch.object(cache_mod.brew_mod, "info_all", return_value=fake_data), \
         patch.object(cache_mod.analytics_mod, "fetch_all", return_value={}), \
         patch.object(cache_mod.analytics_mod, "merge_into_brew_data", return_value=fake_data):
        result = cache_mod.refresh(force=True)
    assert cache_mod.cache_path().exists()
    assert result.outcome is cache_mod.RefreshOutcome.COMPLETE


def test_refresh_reports_lock_contention():
    cache_mod.cache_path().parent.mkdir(parents=True, exist_ok=True)
    with cache_mod.lock_path().open("w") as lock_fh:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = cache_mod.refresh(force=True)

    assert result.outcome is cache_mod.RefreshOutcome.LOCKED


def test_refresh_writes_metadata_and_reports_analytics_failure():
    fake_data = {"formulae": [{"name": "ripgrep"}], "casks": []}
    error = cache_mod.analytics_mod.AnalyticsFetchError("formula_30d", "offline")
    with patch.object(cache_mod.brew_mod, "info_all", return_value=fake_data), \
         patch.object(cache_mod.analytics_mod, "fetch_all", side_effect=error):
        result = cache_mod.refresh(force=True)

    assert result.outcome is cache_mod.RefreshOutcome.METADATA_ONLY
    assert result.analytics_error == "formula_30d: offline"
    assert json.loads(cache_mod.cache_path().read_text())["formulae"][0]["name"] == "ripgrep"


def test_corrupt_cache_warns_and_falls_back_to_seed(capsys):
    cache_mod.cache_path().parent.mkdir(parents=True, exist_ok=True)
    cache_mod.cache_path().write_text("{ not valid json !!!!")

    seed_data = {
        "_brewq_seed": {"schema_version": 1, "generated_at": 1700000000},
        "formulae": [{"name": "ripgrep", "full_name": "ripgrep", "desc": "",
                      "homepage": "", "versions": {"stable": "1.0"},
                      "installed": [], "deprecated": False, "disabled": False,
                      "aliases": []}],
        "casks": [],
    }
    from brewq.seed import SeedMetadata
    with patch.object(cache_mod.seed_mod, "load_resource",
                      return_value=(seed_data, SeedMetadata(schema_version=1, generated_at=1700000000))), \
         patch.object(cache_mod.brew_mod, "storage_roots", side_effect=OSError("no brew")):
        result = cache_mod.load()

    err = capsys.readouterr().err
    assert "cache corrupt" in err
    assert "brewq refresh" in err
    assert result.source == "seed"
