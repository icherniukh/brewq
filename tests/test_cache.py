from __future__ import annotations

import fcntl
import json
import os
import threading
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


def _formula_data(*, installs: int | None = None, complete: bool = False) -> dict:
    formula = {
        "name": "ripgrep",
        "full_name": "ripgrep",
        "desc": "Search tool",
        "homepage": "https://example.test/ripgrep",
        "versions": {"stable": "15.0"},
        "installed": [],
        "deprecated": False,
        "disabled": False,
        "aliases": [],
    }
    if installs is not None:
        formula.update({
            "installs_30d": installs,
            "installs_90d": installs * 3,
            "installs_365d": installs * 12,
        })
    data = {"formulae": [formula], "casks": []}
    if complete:
        data["_brewq_cache"] = {
            "schema_version": 1,
            "analytics_complete": True,
            "repair_needed": False,
        }
    return data


def _seed_data() -> dict:
    data = _formula_data(installs=10)
    data["_brewq_seed"] = {"schema_version": 1, "generated_at": 1_700_000_000}
    return data


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
    _write_cache(Path(os.environ["BREWQ_CACHE_DIR"]), _formula_data(installs=10, complete=True))
    with patch.object(cache_mod.brew_mod, "info_all") as mock_info:
        result = cache_mod.refresh(force=False, max_age=86400)
        mock_info.assert_not_called()
    assert result.outcome is cache_mod.RefreshOutcome.FRESH


def test_refresh_force_calls_brew():
    fake_data = _formula_data()
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
    fake_data = _formula_data()
    error = cache_mod.analytics_mod.AnalyticsFetchError("formula_30d", "offline")
    with patch.object(cache_mod.brew_mod, "info_all", return_value=fake_data), \
         patch.object(cache_mod.analytics_mod, "fetch_all", side_effect=error):
        result = cache_mod.refresh(force=True)

    assert result.outcome is cache_mod.RefreshOutcome.METADATA_ONLY
    assert result.analytics_error == "formula_30d: offline"
    raw = json.loads(cache_mod.cache_path().read_text())
    assert raw["formulae"][0]["name"] == "ripgrep"
    assert raw["_brewq_cache"] == {
        "schema_version": 1,
        "analytics_complete": False,
        "repair_needed": True,
    }


def test_partial_refresh_retains_usable_analytics_and_repair_state():
    _write_cache(Path(os.environ["BREWQ_CACHE_DIR"]), _formula_data(installs=40, complete=True))
    error = cache_mod.analytics_mod.AnalyticsFetchError("formula_30d", "offline")
    with patch.object(cache_mod.brew_mod, "info_all", return_value=_formula_data()), \
         patch.object(cache_mod.analytics_mod, "fetch_all", side_effect=error), \
         patch.object(cache_mod.brew_mod, "storage_roots", side_effect=OSError("no brew")):
        result = cache_mod.refresh(force=True)
        loaded = cache_mod.load()

    assert result.outcome is cache_mod.RefreshOutcome.METADATA_ONLY
    assert loaded.source == "user"
    assert loaded.analytics_complete is False
    assert loaded.repair_needed is True
    assert loaded.requires_refresh is True
    assert loaded.packages[0].installs_30d == 40
    assert loaded.packages[0].installs_90d == 120
    assert loaded.packages[0].installs_365d == 480


def test_nonforce_refresh_repairs_recent_corrupt_cache():
    cache_mod.cache_path().write_text("{not json")
    fresh_data = _formula_data()
    with patch.object(cache_mod.brew_mod, "info_all", return_value=fresh_data) as info, \
         patch.object(cache_mod.analytics_mod, "fetch_all", return_value={}), \
         patch.object(cache_mod.analytics_mod, "merge_into_brew_data"):
        result = cache_mod.refresh(force=False, max_age=86400)

    assert result.outcome is cache_mod.RefreshOutcome.COMPLETE
    info.assert_called_once()
    assert cache_mod.status()["repair_needed"] is False


@pytest.mark.parametrize("invalid", [
    {},
    {"formulae": [], "casks": []},
    {"formulae": [1], "casks": []},
    {"formulae": [{"name": 42}], "casks": []},
    {"formulae": [{"name": "bad", "versions": {"stable": 42}}], "casks": []},
    {"formulae": [], "casks": [{"token": "bad", "artifacts": 42}]},
    {"formulae": [], "casks": [{"token": "bad", "installed": []}]},
])
def test_invalid_or_empty_catalog_falls_back_to_seed(invalid, capsys):
    _write_cache(Path(os.environ["BREWQ_CACHE_DIR"]), invalid)
    from brewq.seed import SeedMetadata
    with patch.object(
        cache_mod.seed_mod,
        "load_resource",
        return_value=(_seed_data(), SeedMetadata(schema_version=1, generated_at=1_700_000_000)),
    ), patch.object(cache_mod.brew_mod, "storage_roots", side_effect=OSError("no brew")):
        loaded = cache_mod.load(now=1_700_000_100)

    assert loaded.source == "seed"
    assert loaded.packages[0].name == "ripgrep"
    assert "cache corrupt" in capsys.readouterr().err


def test_refresh_lock_file_is_stable_but_status_tracks_ownership():
    with patch.object(cache_mod.brew_mod, "info_all", return_value=_formula_data()), \
         patch.object(cache_mod.analytics_mod, "fetch_all", return_value={}), \
         patch.object(cache_mod.analytics_mod, "merge_into_brew_data"):
        cache_mod.refresh(force=True)

    assert cache_mod.lock_path().exists()
    assert cache_mod.status()["locked"] is False


def test_atomic_cache_write_keeps_previous_snapshot_readable():
    previous = _formula_data(installs=10, complete=True)
    replacement = _formula_data(installs=20, complete=True)
    replacement["formulae"][0]["name"] = "fd"
    replacement["formulae"][0]["full_name"] = "fd"
    _write_cache(Path(os.environ["BREWQ_CACHE_DIR"]), previous)
    payload = json.dumps(replacement)
    started = threading.Event()
    release = threading.Event()

    def slow_dump(_data, handle):
        midpoint = len(payload) // 2
        handle.write(payload[:midpoint])
        handle.flush()
        started.set()
        assert release.wait(timeout=5)
        handle.write(payload[midpoint:])

    with patch.object(cache_mod.json, "dump", side_effect=slow_dump), \
         patch.object(cache_mod.brew_mod, "storage_roots", side_effect=OSError("no brew")):
        writer = threading.Thread(
            target=cache_mod._write_json,
            args=(cache_mod.cache_path(), replacement),
        )
        writer.start()
        assert started.wait(timeout=5)
        assert cache_mod.load().packages[0].name == "ripgrep"
        release.set()
        writer.join(timeout=5)

    assert not writer.is_alive()
    assert json.loads(cache_mod.cache_path().read_text())["formulae"][0]["name"] == "fd"


def test_load_holds_shared_lock_until_pickle_matches_snapshot():
    _write_cache(Path(os.environ["BREWQ_CACHE_DIR"]), _formula_data(installs=10, complete=True))
    started = threading.Event()
    release = threading.Event()
    loaded = []

    def slow_inventory(packages, roots=None):
        started.set()
        assert release.wait(timeout=5)
        return None

    def read_cache():
        loaded.append(cache_mod.load())

    with patch.object(cache_mod, "_overlay_inventory", side_effect=slow_inventory), \
         patch.object(cache_mod.brew_mod, "info_all") as info:
        reader = threading.Thread(target=read_cache)
        reader.start()
        assert started.wait(timeout=5)
        result = cache_mod.refresh(force=True)
        release.set()
        reader.join(timeout=5)

    assert not reader.is_alive()
    assert result.outcome is cache_mod.RefreshOutcome.LOCKED
    info.assert_not_called()
    assert loaded[0].packages[0].name == "ripgrep"
    assert cache_mod.pickle_path().exists()


def test_foreground_bootstrap_uses_refresh_lock():
    operations = []

    def record_lock(_handle, operation):
        operations.append(operation)

    with patch.object(cache_mod.fcntl, "flock", side_effect=record_lock), \
         patch.object(cache_mod.brew_mod, "info_all", return_value=_formula_data()):
        loaded = cache_mod.foreground_bootstrap(timeout=7)

    assert loaded.repair_needed is True
    assert operations == [fcntl.LOCK_EX, fcntl.LOCK_UN]


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
