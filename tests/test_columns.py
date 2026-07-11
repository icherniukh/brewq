from __future__ import annotations

import pytest

from brewq.columns import (
    _merge_user_presets,
    list_profiles,
    pick_representative_metric,
    resolve,
    search_profiles,
)
from brewq.model import Package


def _pkg(**kw) -> Package:
    defaults = {
        "name": "test", "type": "formula", "description": "A tool",
        "url": "https://example.com", "version": "1.0",
        "installs_30d": 1_234, "installs_90d": 4_000, "installs_365d": 15_000,
        "installed": False, "deprecated": False, "disabled": False,
    }
    defaults.update(kw)
    return Package(**defaults)


def test_resolve_profile():
    cols = resolve("compact", [])
    keys = [c.key for c in cols]
    assert keys == ["name", "installs_90d", "description"]


def test_resolve_full_profile_includes_all_windows():
    cols = resolve("full", [])
    keys = [c.key for c in cols]
    assert keys == ["name", "type", "version", "installs_30d", "installs_90d", "installs_365d", "installed", "status", "description"]



def test_resolve_list_compact_profile():
    cols = resolve("compact", [], profiles={"compact": ["name", "type", "description"]})
    assert [c.key for c in cols] == ["name", "type", "description"]


def test_resolve_custom_list():
    cols = resolve("name,type,url", [])
    assert [c.key for c in cols] == ["name", "type", "url"]


def test_version_display_truncates_long_versions():
    pkg = _pkg(version="20240203-110809,5046fc22")
    cols = resolve("version", [])
    assert cols[0].getter(pkg) == "20240203-1…5046fc22"


def test_version_raw_keeps_full_version():
    pkg = _pkg(version="20240203-110809,5046fc22")
    cols = resolve("version", [])
    assert cols[0].raw_getter is not None
    assert cols[0].raw_getter(pkg) == "20240203-110809,5046fc22"


def test_resolve_alias_trending():
    cols = resolve("trending", ["name"])
    assert cols[0].key == "trending"


def test_resolve_alias_trend():
    cols = resolve("trend", ["name"])
    assert cols[0].key == "trending"


def test_resolve_alias_hot():
    cols = resolve("hot", ["name"])
    assert cols[0].key == "trending"


def test_resolve_alias_popularity_maps_to_trending():
    cols = resolve("popularity", ["name"])
    assert cols[0].key == "trending"


def test_resolve_auto_uses_representative_metric():
    cols = resolve(["name", "auto"], [], representative_metric="installs_90d")
    assert [c.key for c in cols] == ["name", "installs_90d"]


def test_resolve_auto_without_metric_falls_back_to_90d():
    cols = resolve(["auto"], [])
    assert cols[0].key == "installs_90d"


def test_resolve_alias_installs():
    cols = resolve("installs", [])
    assert cols[0].key == "installs_30d"


def test_resolve_alias_30d():
    cols = resolve("30d", [])
    assert cols[0].key == "installs_30d"


def test_resolve_alias_i30():
    cols = resolve("i30", [])
    assert cols[0].key == "installs_30d"


def test_resolve_alias_90d():
    cols = resolve("90d", [])
    assert cols[0].key == "installs_90d"


def test_resolve_alias_i90():
    cols = resolve("i90", [])
    assert cols[0].key == "installs_90d"


def test_resolve_alias_365d():
    cols = resolve("365d", [])
    assert cols[0].key == "installs_365d"


def test_resolve_alias_i365():
    cols = resolve("i365", [])
    assert cols[0].key == "installs_365d"


def test_resolve_alias_y():
    cols = resolve("y", [])
    assert cols[0].key == "installs_365d"


def test_resolve_alias_ver():
    cols = resolve("ver", [])
    assert cols[0].key == "version"


def test_resolve_alias_v():
    cols = resolve("v", [])
    assert cols[0].key == "version"


def test_resolve_alias_desc():
    cols = resolve("desc", [])
    assert cols[0].key == "description"


def test_resolve_alias_inst():
    cols = resolve("inst", [])
    assert cols[0].key == "installed"


def test_resolve_alias_homepage():
    cols = resolve("homepage", [])
    assert cols[0].key == "url"


def test_resolve_unknown_raises():
    with pytest.raises(ValueError, match="Unknown column"):
        resolve("bogus_col", [])


def test_installs_30d_display_with_comma():
    pkg = _pkg(installs_30d=528_018)
    cols = resolve("installs_30d", [])
    assert cols[0].getter(pkg) == "528,018"


def test_installs_30d_display_unknown():
    pkg = _pkg(installs_30d=-1)
    cols = resolve("installs_30d", [])
    assert cols[0].getter(pkg) == "-"


def test_installs_alias_reads_30d():
    pkg = _pkg(installs_30d=1_000, installs_365d=12_000)
    cols = resolve("installs", [])
    assert cols[0].getter(pkg) == "1,000"


def test_installs_365d_column_reads_365d():
    pkg = _pkg(installs_30d=100, installs_365d=5_000)
    cols = resolve("installs_365d", [])
    assert cols[0].getter(pkg) == "5,000"


def test_installs_90d_column_reads_90d():
    pkg = _pkg(installs_30d=100, installs_90d=3_000, installs_365d=12_000)
    cols = resolve("installs_90d", [])
    assert cols[0].getter(pkg) == "3,000"


def test_installs_90d_header():
    cols = resolve("installs_90d", [])
    assert cols[0].header == "90d"


def test_installs_365d_header():
    cols = resolve("installs_365d", [])
    assert cols[0].header == "365d"


def test_installs_30d_header():
    cols = resolve("installs_30d", [])
    assert cols[0].header == "30d"


def test_resolve_default_uses_config():
    cols = resolve("default", ["name", "type"])
    assert [c.key for c in cols] == ["name", "type"]


def test_trending_display_formats_as_multiplier():
    pkg = _pkg(installs_30d=200, installs_90d=200, installs_365d=800)
    cols = resolve("trending", [])
    text = cols[0].getter(pkg)
    assert text.endswith("x")
    assert text[:-1].replace(".", "", 1).isdigit()


def test_trending_display_unknown_when_no_history():
    pkg = _pkg(installs_30d=200, installs_90d=-1, installs_365d=-1)
    cols = resolve("trending", [])
    assert cols[0].getter(pkg) == "-"


def test_pick_representative_metric_prefers_90d():
    pkg = _pkg(installs_30d=100, installs_90d=300, installs_365d=1_000)
    assert pick_representative_metric(pkg) == "installs_90d"


def test_pick_representative_metric_falls_back_to_30d():
    pkg = _pkg(installs_30d=300, installs_90d=-1, installs_365d=1_000)
    assert pick_representative_metric(pkg) == "installs_30d"


def test_pick_representative_metric_falls_back_to_365d():
    pkg = _pkg(installs_30d=-1, installs_90d=-1, installs_365d=1_000)
    assert pick_representative_metric(pkg) == "installs_365d"


def test_pick_representative_metric_defaults_when_no_data_at_all():
    pkg = _pkg(installs_30d=-1, installs_90d=-1, installs_365d=-1)
    assert pick_representative_metric(pkg) == "installs_90d"


def test_pick_representative_metric_handles_none_package():
    assert pick_representative_metric(None) == "installs_90d"


class TestMergeUserPresets:
    def test_no_user_presets_returns_builtins(self):
        assert _merge_user_presets({"a": ["name"]}, {}) == {"a": ["name"]}

    def test_user_override_beats_builtin(self):
        builtin = {"compact": ["name", "installs_90d"]}
        user = {"compact": ["name", "trending"]}
        assert _merge_user_presets(builtin, user) == {"compact": ["name", "trending"]}

    def test_user_adds_new_preset(self):
        builtin = {"compact": ["name"]}
        user = {"ops": ["name", "type", "version"]}
        merged = _merge_user_presets(builtin, user)
        assert merged["compact"] == ["name"]
        assert merged["ops"] == ["name", "type", "version"]

    def test_skips_non_list_values(self):
        merged = _merge_user_presets({"compact": ["name"]}, {"bad": "string"})
        assert "bad" not in merged

    def test_skips_empty_list(self):
        merged = _merge_user_presets({"compact": ["name"]}, {"empty": []})
        assert "empty" not in merged

    def test_skips_mixed_list_with_non_strings(self):
        merged = _merge_user_presets({"compact": ["name"]}, {"bad": ["name", 42]})
        assert "bad" not in merged

    def test_preserves_builtin_when_user_has_non_list(self):
        merged = _merge_user_presets({"compact": ["name"]}, {"compact": "not-a-list"})
        assert merged["compact"] == ["name"]

    def test_empty_user_dict_returns_same_keys(self):
        merged = _merge_user_presets({"x": ["y"]}, {})
        assert list(merged) == ["x"]


class TestSearchProfiles:
    def test_returns_search_profiles_with_no_user_presets(self):
        profiles = search_profiles()
        assert "compact" in profiles
        assert "full" in profiles

    def test_merges_user_presets_into_search_profiles(self):
        profiles = search_profiles({"ops": ["name", "type"]})
        assert profiles["ops"] == ["name", "type"]
        assert "compact" in profiles


class TestListProfiles:
    def test_returns_list_profiles_with_no_user_presets(self):
        profiles = list_profiles()
        assert "compact" in profiles
        assert "full" in profiles

    def test_merges_user_presets_into_list_profiles(self):
        profiles = list_profiles({"links": ["name", "url"]})
        assert profiles["links"] == ["name", "url"]
        assert "compact" in profiles
