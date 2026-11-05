from __future__ import annotations

import gzip
import json
import re
import runpy
from pathlib import Path
from unittest.mock import patch

import pytest

from brewq import cache, seed
from brewq.inventory import InstalledRecord, InventoryScan


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


@pytest.fixture
def sanitize_seed():
    script = Path(__file__).resolve().parents[1] / "scripts" / "build-seed-cache.py"
    return runpy.run_path(str(script))["_sanitize"]


@pytest.mark.parametrize("home", ["/Users/example.user", "/home/example+builder", "/Users/构建者"])
def test_builder_sanitizes_nested_home_paths_and_installed_state(monkeypatch, sanitize_seed, home):
    monkeypatch.setenv("HOME", home)
    data = _data()
    formula = data["formulae"][0]
    formula["installed"] = [{"version": "14.1", "prefix": f"{home}/Cellar/ripgrep"}]
    formula["service"] = {"run": [f"{home}/bin/rg", "--flag"], "working_dir": home}
    formula["caveats"] = f'Use "{home}" or ({home}) and {home}/.config/rg'
    formula["upstream_examples"] = [
        "/Users/Shared/public", "/home/upstream-user/example",
        f"{home}-other/config", f"{home}.backup/config", f"{home}_other/config",
        f"{home}+other/config", f"/archive{home}/config",
        f"https://example.test{home}/config",
    ]
    cask = data["casks"][0]
    cask["installed"] = "124.0"
    cask["artifacts"] = [
        {"app": ["Browser.app", {"target": f"{home}/Applications/Browser.app"}]},
        {"binary": ["bin/browser", {"target": "browser-tool"}]},
    ]
    data["nested"] = {f"{home}/key": [True, None, 7, 1.5]}
    examples = list(formula["upstream_examples"])

    sanitize_seed(data)

    formula, cask = data["formulae"][0], data["casks"][0]
    assert formula["installed"] == [] and cask["installed"] is None
    assert formula["service"] == {"run": ["~/bin/rg", "--flag"], "working_dir": "~"}
    assert formula["caveats"] == 'Use "~" or (~) and ~/.config/rg'
    assert formula["upstream_examples"] == examples
    assert cask["artifacts"][0]["app"][1]["target"] == "~/Applications/Browser.app"
    assert data["nested"] == {"~/key": [True, None, 7, 1.5]}
    assert cask["artifacts"][1]["binary"][1]["target"] == "browser-tool"
    for group in ("formulae", "casks"):
        for key, value in _data()[group][0].items():
            assert data[group][0][key] == value
    encoded = seed.encode(data, generated_at=1_700_000_000)
    sanitize_seed(data)
    assert seed.encode(data, generated_at=1_700_000_000) == encoded


def test_builder_rejects_redacted_key_collisions_without_mutation(monkeypatch, sanitize_seed):
    monkeypatch.setenv("HOME", "/home/seed-builder")
    data = _data()
    data["paths"] = {"/home/seed-builder/tool": 1, "~/tool": 2}
    original = json.dumps(data)

    with pytest.raises(ValueError, match="collision"):
        sanitize_seed(data)

    assert json.dumps(data) == original


def test_builder_root_home_does_not_redact_all_absolute_paths(monkeypatch, sanitize_seed):
    monkeypatch.setenv("HOME", "/")
    data = _data()
    data["formulae"][0]["caveats"] = "/usr/local/bin; https://example.test/path"

    sanitize_seed(data)

    assert data["formulae"][0]["caveats"] == "/usr/local/bin; https://example.test/path"


def test_packaged_seed_has_no_unreviewed_home_paths_or_installed_state():
    data, _ = seed.load_resource()
    # Detect another builder's account too. Shared system paths and home-like
    # segments inside public URLs are not local user-profile destinations.
    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for key, item in value.items():
                yield key
                yield from strings(item)
        elif isinstance(value, list):
            for item in value:
                yield from strings(item)

    unreviewed_paths = sum(
        len(re.findall(
            r'''(?:^|[\s"'(<=>])/(?:Users/(?!Shared(?:/|$|["\s]))|home/)[^/\s"'<>]+''',
            text,
        ))
        for text in strings(data)
    )
    assert unreviewed_paths == 0
    assert all(record["installed"] == [] for record in data["formulae"])
    assert all(record["installed"] is None for record in data["casks"])


def test_encode_is_deterministic_and_valid():
    first = seed.encode(_data(), generated_at=1_700_000_000)
    second = seed.encode(_data(), generated_at=1_700_000_000)

    assert first == second
    decoded = json.loads(gzip.decompress(first))
    metadata = seed.validate(decoded)
    assert metadata.schema_version == 1
    assert metadata.generated_at == 1_700_000_000


def test_packaged_seed_is_present_and_populated():
    data, metadata = seed.load_resource()

    assert metadata.schema_version == 1
    assert len(data["formulae"]) > 8_000
    assert len(data["casks"]) > 7_000


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
    inventory = InventoryScan(
        {("formula", "ripgrep"): InstalledRecord("ripgrep", "formula", "14.1")},
        frozenset({"formula", "cask"}),
    )
    with patch("brewq.seed.load_resource", return_value=(_data(), metadata)), \
         patch("brewq.brew.storage_roots", return_value=(Path("/cellar"), Path("/caskroom"))), \
         patch("brewq.inventory.scan", return_value=inventory):
        loaded = cache.load(now=1_700_000_100)

    ripgrep = next(package for package in loaded.packages if package.name == "ripgrep")
    assert loaded.source == "seed"
    assert loaded.age_seconds == 100
    assert ripgrep.installed is True
    assert ripgrep.version == "15.0"
    assert ripgrep.installed_version == "14.1"


def test_invalid_user_cache_falls_back_to_seed(tmp_path, monkeypatch):
    monkeypatch.setenv("BREWQ_CACHE_DIR", str(tmp_path))
    cache.cache_path().write_text("not json")
    metadata = seed.SeedMetadata(schema_version=1, generated_at=1_700_000_000)
    with patch("brewq.seed.load_resource", return_value=(_data(), metadata)), \
         patch("brewq.brew.storage_roots", side_effect=FileNotFoundError):
        loaded = cache.load(now=1_700_000_100)

    assert loaded.source == "seed"
    assert {package.name for package in loaded.packages} == {"ripgrep", "firefox"}
