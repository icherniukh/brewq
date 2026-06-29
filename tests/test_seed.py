from __future__ import annotations

import gzip
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from brewq import cache, seed
from brewq.inventory import InstalledRecord


def _data() -> dict:
    metrics = {"installs_30d": 10, "installs_90d": 30, "installs_365d": 120}
    return {
        "formulae": [{
            "name": "ripgrep",
            "full_name": "ripgrep",
            "desc": "Search tool",
            "homepage": "https://example.test/ripgrep",
            "versions": {"stable": "15.0"},
            "installed": [],
            **metrics,
        }],
        "casks": [{
            "token": "firefox",
            "name": ["Firefox"],
            "desc": "Browser",
            "homepage": "https://example.test/firefox",
            "version": "125.0",
            "installed": None,
            **metrics,
        }],
    }


def test_encode_is_deterministic_and_valid():
    first = seed.encode(_data(), generated_at=1_700_000_000)
    second = seed.encode(_data(), generated_at=1_700_000_000)

    assert first == second
    decoded = json.loads(gzip.decompress(first))
    metadata = seed.validate(decoded)
    assert metadata.schema_version == 1
    assert metadata.generated_at == 1_700_000_000


def test_validate_rejects_missing_analytics():
    data = _data()
    del data["formulae"][0]["installs_90d"]
    data["_brewq_seed"] = {"schema_version": 1, "generated_at": 1_700_000_000}

    with pytest.raises(seed.SeedError, match="installs_90d"):
        seed.validate(data)


def test_cache_load_prefers_valid_user_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("BREWQ_CACHE_DIR", str(tmp_path))
    cache.cache_path().write_text(json.dumps(_data()))

    with patch("brewq.seed.load_resource", side_effect=AssertionError("used seed")):
        loaded = cache.load()

    assert loaded.source == "user"
    assert loaded.packages[0].name == "ripgrep"


def test_cache_loads_seed_and_overlays_installed_state(tmp_path, monkeypatch):
    monkeypatch.setenv("BREWQ_CACHE_DIR", str(tmp_path))
    metadata = seed.SeedMetadata(schema_version=1, generated_at=1_700_000_000)
    records = {
        ("formula", "ripgrep"): InstalledRecord("ripgrep", "formula", "14.1"),
    }
    with patch("brewq.seed.load_resource", return_value=(_data(), metadata)), \
         patch("brewq.brew.storage_roots", return_value=(Path("/cellar"), Path("/caskroom"))), \
         patch("brewq.inventory.scan", return_value=records):
        loaded = cache.load(now=1_700_000_100)

    ripgrep = next(package for package in loaded.packages if package.name == "ripgrep")
    assert loaded.source == "seed"
    assert loaded.age_seconds == 100
    assert ripgrep.installed is True
    assert ripgrep.version == "14.1"


def test_invalid_user_cache_falls_back_to_seed(tmp_path, monkeypatch):
    monkeypatch.setenv("BREWQ_CACHE_DIR", str(tmp_path))
    cache.cache_path().write_text("not json")
    metadata = seed.SeedMetadata(schema_version=1, generated_at=1_700_000_000)
    with patch("brewq.seed.load_resource", return_value=(_data(), metadata)), \
         patch("brewq.brew.storage_roots", side_effect=FileNotFoundError):
        loaded = cache.load(now=1_700_000_100)

    assert loaded.source == "seed"
    assert {package.name for package in loaded.packages} == {"ripgrep", "firefox"}
