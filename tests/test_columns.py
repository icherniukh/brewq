from __future__ import annotations

import pytest

from brewq.columns import FULL_COLUMNS, pick_representative_metric, resolve, select, with_url
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


def test_full_columns_resolve():
    cols = resolve(list(FULL_COLUMNS), [])
    keys = [c.key for c in cols]
    assert keys == [
        "name", "type", "version", "installed", "status",
        "installs_30d", "installs_90d", "installs_365d", "trending",
        "binaries", "url", "description",
    ]


def test_with_url_inserts_before_description():
    cols = resolve("name,installs_90d,description", [])
    keys = [c.key for c in with_url(cols)]
    assert keys == ["name", "installs_90d", "url", "description"]


def test_with_url_appends_without_description():
    cols = resolve("name,installs_90d", [])
    keys = [c.key for c in with_url(cols)]
    assert keys == ["name", "installs_90d", "url"]


def test_with_url_is_idempotent():
    cols = resolve("name,url,description", [])
    keys = [c.key for c in with_url(cols)]
    assert keys == ["name", "url", "description"]


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


def test_version_prefers_installed_version_for_installed_package():
    pkg = _pkg(version="available")
    pkg.installed = True
    pkg.installed_version = "installed"
    col = resolve("version", [])[0]
    assert col.getter(pkg) == "installed"
    assert col.raw_getter is not None
    assert col.raw_getter(pkg) == "installed"


def test_resolve_alias_trending():
    cols = resolve("trending", ["name"])
    assert cols[0].key == "trending"


def test_resolve_alias_trend():
    cols = resolve("trend", ["name"])
    assert cols[0].key == "trending"


def test_resolve_alias_hot():
    cols = resolve("hot", ["name"])
    assert cols[0].key == "trending"


@pytest.mark.parametrize("alias", ["pop", "popularity", "score", "rank"])
def test_misleading_trend_aliases_are_rejected(alias):
    with pytest.raises(ValueError, match="Unknown column"):
        resolve(alias, ["name"])


def test_resolve_auto_uses_representative_metric():
    cols = resolve(["name", "auto"], [], representative_metric="installs_90d")
    assert [c.key for c in cols] == ["name", "installs_90d"]


def test_resolve_auto_without_metric_falls_back_to_90d():
    cols = resolve(["auto"], [])
    assert cols[0].key == "installs_90d"


def test_resolve_auto_can_be_reserved_for_configuration():
    with pytest.raises(ValueError, match="only available in search configuration"):
        resolve("auto", [], allow_auto=False)


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
    with pytest.raises(ValueError, match="Unknown column") as error:
        resolve("bogus_col", [])
    assert "installs_90d" in str(error.value)
    assert "homepage" not in str(error.value)


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


@pytest.mark.parametrize(
    ("spec", "expected"),
    [("+version,bin", ["name", "installs_90d", "trending", "version", "binaries", "description"]),
     ("+home,-trend", ["name", "installs_90d", "url", "description"]),
     ("-trend,desc", ["name", "installs_90d"]),
     ("+90d,i90", ["name", "installs_90d", "trending", "description"]),
     ("-bin,+version,-ver,+ver", ["name", "installs_90d", "trending", "version", "description"]),
     ("name,version,90d", ["name", "version", "installs_90d"])],
)
def test_column_layout_edits_and_exact_order(spec, expected):
    defaults = ["name", "installs_90d", "trending", "description"]
    assert [col.key for col in select(spec, defaults)] == expected
    assert defaults == ["name", "installs_90d", "trending", "description"]


def test_column_edits_resolve_config_auto_with_representative_metric():
    assert [col.key for col in select(
        "+version", ["name", "auto", "description"], "installs_365d",
    )] == ["name", "installs_365d", "version", "description"]


def test_added_field_appends_when_description_absent():
    assert [col.key for col in select("+bin", ["name"])] == ["name", "binaries"]


def test_all_uses_full_field_order():
    assert [col.key for col in select("all", ["name"])] == FULL_COLUMNS


@pytest.mark.parametrize("spec", ["+", "-", "+bogus", "+version,", "+auto", "-auto"])
def test_invalid_column_edits_are_rejected(spec):
    with pytest.raises(ValueError):
        select(spec, ["name"])


def test_removing_every_column_is_rejected():
    with pytest.raises(ValueError, match="at least one field"):
        select("-name,desc", ["name", "description"])
