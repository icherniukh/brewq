from __future__ import annotations

import pytest

from brewq.columns import (
    CANONICAL_COLUMNS,
    FULL_COLUMNS,
    pick_representative_metric,
    resolve,
    select,
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



def test_resolve_custom_list():
    cols = resolve("name,type,url", [])
    assert [c.key for c in cols] == ["name", "type", "url"]


def test_version_display_truncates_long_versions():
    pkg = _pkg(version="20240203-110809,5046fc22")
    cols = resolve("ver", [])
    assert cols[0].getter(pkg) == "20240203-1…5046fc22"


def test_version_raw_keeps_full_version():
    pkg = _pkg(version="20240203-110809,5046fc22")
    cols = resolve("ver", [])
    assert cols[0].raw_getter is not None
    assert cols[0].raw_getter(pkg) == "20240203-110809,5046fc22"


def test_version_prefers_installed_version_for_installed_package():
    pkg = _pkg(version="available")
    pkg.installed = True
    pkg.installed_version = "installed"
    col = resolve("ver", [])[0]
    assert col.getter(pkg) == "installed"
    assert col.raw_getter is not None
    assert col.raw_getter(pkg) == "installed"


def test_resolve_auto_uses_representative_metric():
    cols = resolve(["name", "auto"], [], representative_metric="90d")
    assert [c.key for c in cols] == ["name", "90d"]


def test_resolve_auto_without_metric_falls_back_to_90d():
    cols = resolve(["auto"], [])
    assert cols[0].key == "90d"


def test_resolve_auto_can_be_reserved_for_configuration():
    with pytest.raises(ValueError, match="only available in search configuration"):
        resolve("auto", [], allow_auto=False)


def test_resolve_unknown_raises():
    with pytest.raises(ValueError, match="Unknown column") as error:
        resolve("bogus_col", [])
    assert "90d" in str(error.value)
    assert "homepage" not in str(error.value)


def test_installs_30d_display_with_comma():
    pkg = _pkg(installs_30d=528_018)
    cols = resolve("30d", [])
    assert cols[0].getter(pkg) == "528,018"


def test_installs_30d_display_unknown():
    pkg = _pkg(installs_30d=-1)
    cols = resolve("30d", [])
    assert cols[0].getter(pkg) == "-"


def test_installs_365d_column_reads_365d():
    pkg = _pkg(installs_30d=100, installs_365d=5_000)
    cols = resolve("365d", [])
    assert cols[0].getter(pkg) == "5,000"


def test_installs_90d_column_reads_90d():
    pkg = _pkg(installs_30d=100, installs_90d=3_000, installs_365d=12_000)
    cols = resolve("90d", [])
    assert cols[0].getter(pkg) == "3,000"


def test_installs_90d_header():
    cols = resolve("90d", [])
    assert cols[0].header == "90d"


def test_installs_365d_header():
    cols = resolve("365d", [])
    assert cols[0].header == "365d"


def test_installs_30d_header():
    cols = resolve("30d", [])
    assert cols[0].header == "30d"


def test_resolve_default_uses_config():
    cols = resolve("default", ["name", "type"])
    assert [c.key for c in cols] == ["name", "type"]


def test_trending_display_formats_as_multiplier():
    pkg = _pkg(installs_30d=200, installs_90d=200, installs_365d=800)
    cols = resolve("trend", [])
    text = cols[0].getter(pkg)
    assert text.endswith("x")
    assert text[:-1].replace(".", "", 1).isdigit()


def test_trending_display_unknown_when_no_history():
    pkg = _pkg(installs_30d=200, installs_90d=-1, installs_365d=-1)
    cols = resolve("trend", [])
    assert cols[0].getter(pkg) == "-"


def test_pick_representative_metric_prefers_90d():
    pkg = _pkg(installs_30d=100, installs_90d=300, installs_365d=1_000)
    assert pick_representative_metric(pkg) == "90d"


def test_pick_representative_metric_falls_back_to_30d():
    pkg = _pkg(installs_30d=300, installs_90d=-1, installs_365d=1_000)
    assert pick_representative_metric(pkg) == "30d"


def test_pick_representative_metric_falls_back_to_365d():
    pkg = _pkg(installs_30d=-1, installs_90d=-1, installs_365d=1_000)
    assert pick_representative_metric(pkg) == "365d"


def test_pick_representative_metric_defaults_when_no_data_at_all():
    pkg = _pkg(installs_30d=-1, installs_90d=-1, installs_365d=-1)
    assert pick_representative_metric(pkg) == "90d"


def test_pick_representative_metric_handles_none_package():
    assert pick_representative_metric(None) == "90d"


@pytest.mark.parametrize("old", [
    "n", "t", "v", "version",
    "30", "i30", "installs", "installs_30d",
    "90", "i90", "installs_90d",
    "365", "i365", "y", "year",
    "installs_365d", "trending", "hot",
    "binaries", "bins", "description", "d",
    "installed", "i", "h", "home", "homepage",
])
def test_old_field_names_are_unknown(old):
    with pytest.raises(ValueError, match="Unknown column"):
        resolve(old, [])



@pytest.mark.parametrize("name", CANONICAL_COLUMNS)
def test_field_name_equals_lowercase_header(name):
    col = resolve(name, [])[0]
    assert col.key == col.header.lower() == name



@pytest.mark.parametrize("spec,expected", [
    ("name,ver,90d", ["name", "ver", "90d"]),
    ("default,url", ["name", "90d", "trend", "desc", "url"]),
    ("url,default", ["url", "name", "90d", "trend", "desc"]),
    ("default,name", ["name", "90d", "trend", "desc"]),
    ("url,default,url", ["url", "name", "90d", "trend", "desc"]),
    ("name,name,ver", ["name", "ver"]),
])
def test_ordered_selection_and_first_occurrence(spec, expected):
    defaults = ["name", "90d", "trend", "desc"]
    assert [col.key for col in select(spec, defaults)] == expected
    assert defaults == ["name", "90d", "trend", "desc"]



def test_default_expands_configured_view():
    assert [c.key for c in select("url,default", ["name", "ver"])] == ["url", "name", "ver"]
    assert [c.key for c in select("default,365d", ["name", "auto"], "365d")] == ["name", "365d"]



@pytest.mark.parametrize("tsv", [False, True])
def test_all_is_mode_aware(tsv):
    expected = FULL_COLUMNS if tsv else [key for key in FULL_COLUMNS if key not in {"inst", "status"}]
    assert [c.key for c in select("all", ["name"], tsv=tsv)] == expected



@pytest.mark.parametrize("name", ["inst", "status"])
def test_tsv_only_fields_rejected_in_table_mode(name):
    with pytest.raises(ValueError, match=f"{name!r} is TSV-only; use --tsv"):
        select(name, ["name"])
    assert select(name, [], tsv=True)[0].key == name
    with pytest.raises(ValueError, match="TSV-only"):
        select("default", ["name", name])



@pytest.mark.parametrize("spec,equivalent", [
    ("+url,-trend", "name,90d,url,desc"),
    ("+url", "name,90d,trend,url,desc"),
    ("+ver,bin", "name,90d,trend,ver,bin,desc"),
    ("-trend,bin", "name,90d,desc"),
    ("-desc", "name,90d,trend"),
    ("name,+url", "name,90d,trend,url,desc"),
])
def test_signed_tokens_rejected_with_full_equivalent_list(spec, equivalent):
    with pytest.raises(ValueError, match=f"use -c {equivalent}"):
        select(spec, ["name", "90d", "trend", "desc"])



@pytest.mark.parametrize("spec", ["+", "-", "+bogus", "+version", "-version", "+ver,", "name,", "", "help"])
def test_invalid_column_lists(spec):
    with pytest.raises(ValueError):
        select(spec, ["name"])



@pytest.mark.parametrize("typo,expected", [("naem", "name"), ("trned", "trend"), ("NAME", "name")])
def test_field_typos_suggest_without_resolving(typo, expected):
    with pytest.raises(ValueError, match=f"Did you mean {expected!r}"):
        select(typo, ["name"])
