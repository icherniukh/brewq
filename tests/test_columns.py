from __future__ import annotations

import pytest

from brewq.columns import resolve
from brewq.model import Package


def _pkg(**kw) -> Package:
    defaults = {
        "name": "test", "type": "formula", "description": "A tool",
        "url": "https://example.com", "version": "1.0",
        "installs_30d": 1_234, "installs_365d": 15_000,
        "installed": False, "deprecated": False, "disabled": False,
    }
    defaults.update(kw)
    return Package(**defaults)


def test_resolve_profile():
    cols = resolve("compact", [])
    keys = [c.key for c in cols]
    assert keys == ["name", "installs", "description"]


def test_resolve_custom_list():
    cols = resolve("name,type,url", [])
    assert [c.key for c in cols] == ["name", "type", "url"]


def test_resolve_alias_popularity():
    cols = resolve("popularity", ["name"])
    assert cols[0].key == "installs"


def test_resolve_alias_homepage():
    cols = resolve("homepage", [])
    assert cols[0].key == "url"


def test_resolve_unknown_raises():
    with pytest.raises(ValueError, match="Unknown column"):
        resolve("bogus_col", [])


def test_installs_display_with_comma():
    pkg = _pkg(installs_30d=528_018)
    cols = resolve("installs", [])
    val = cols[0].getter(pkg, "installs-30d")
    assert val == "528,018"


def test_installs_display_unknown():
    pkg = _pkg(installs_30d=-1)
    cols = resolve("installs", [])
    assert cols[0].getter(pkg, "installs-30d") == "-"


def test_installs_365d_uses_year_metric():
    pkg = _pkg(installs_30d=100, installs_365d=5_000)
    cols = resolve("installs", [])
    assert cols[0].getter(pkg, "installs-365d") == "5,000"


def test_resolve_default_uses_config():
    cols = resolve("default", ["name", "type"])
    assert [c.key for c in cols] == ["name", "type"]
