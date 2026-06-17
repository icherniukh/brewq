from __future__ import annotations

import pytest

from brewq.columns import resolve
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
    assert keys == ["name", "installs_30d", "description"]


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


def test_resolve_alias_popularity():
    cols = resolve("popularity", ["name"])
    assert cols[0].key == "popularity"


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
    assert cols[0].header == "90D"


def test_installs_365d_header():
    cols = resolve("installs_365d", [])
    assert cols[0].header == "365D"


def test_installs_30d_header():
    cols = resolve("installs_30d", [])
    assert cols[0].header == "30D"


def test_resolve_default_uses_config():
    cols = resolve("default", ["name", "type"])
    assert [c.key for c in cols] == ["name", "type"]
