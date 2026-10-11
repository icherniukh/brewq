from __future__ import annotations

import argparse

import pytest

from brewq.model import Package
from brewq.options import (
    ListOptions,
    SearchOptions,
    build_search_options,
    parse_sort,
    rank,
    rank_installed,
)


def _pkg(name: str, type_: str = "formula", installs_30d: int = -1,
         installs_90d: int = -1, installs_365d: int = -1, desc: str = "",
         deprecated: bool = False, disabled: bool = False,
         aliases: list[str] | None = None, installed: bool = False) -> Package:
    return Package(
        name=name, type=type_, description=desc, url="",
        version="1.0", installs_30d=installs_30d, installs_90d=installs_90d,
        installs_365d=installs_365d,
        installed=installed, deprecated=deprecated, disabled=disabled,
        aliases=aliases or [],
    )


pkgs = [
    _pkg("ripgrep",     installs_30d=80_000, installs_90d=240_000, desc="Search tool like grep"),
    _pkg("ripgrep-all", installs_30d=10_000, installs_90d=30_000,  desc="ripgrep variant for all file types"),
    _pkg("rg-tools",    installs_30d=500,    installs_90d=1_500,   desc="Helper tools"),
    _pkg("bat",         installs_30d=50_000, installs_90d=150_000, desc="Clone of cat with wings"),
    _pkg("somecask",    type_="cask", installs_30d=5_000, installs_90d=15_000),
]


# --- parse_sort ---

def test_parse_sort_canonical():
    assert parse_sort("installs_30d") == "installs_30d"
    assert parse_sort("installs_365d") == "installs_365d"
    assert parse_sort("name") == "name"


def test_parse_sort_30d_aliases():
    for alias in ("30", "30d", "i30", "installs"):
        assert parse_sort(alias) == "installs_30d", f"alias {alias!r} failed"


def test_parse_sort_90d_aliases():
    for alias in ("90", "90d", "i90"):
        assert parse_sort(alias) == "installs_90d", f"alias {alias!r} failed"


def test_parse_sort_365d_aliases():
    for alias in ("365", "365d", "i365", "y", "year"):
        assert parse_sort(alias) == "installs_365d", f"alias {alias!r} failed"


def test_parse_sort_name_aliases():
    for alias in ("n", "nm", "alpha", "name"):
        assert parse_sort(alias) == "name", f"alias {alias!r} failed"


def test_parse_sort_case_insensitive():
    assert parse_sort("30D") == "installs_30d"
    assert parse_sort("NAME") == "name"
    assert parse_sort("Y") == "installs_365d"


def test_parse_sort_unknown_raises():
    with pytest.raises(ValueError, match="Unknown sort field") as error:
        parse_sort("bogus")
    assert str(error.value).endswith("Valid: 90d, 30d, 365d, trending, name")
    assert "i90" not in str(error.value)


# --- rank ---

def test_rank_by_installs_30d():
    opts = SearchOptions(query=["ripgrep"], sort="installs_30d")
    result = rank(list(pkgs), opts)
    assert result[0].name == "ripgrep"


def test_rank_by_trending_prefers_higher_trend_score():
    local = [
        _pkg("declining-tool", installs_30d=50, installs_90d=600, installs_365d=3_000),
        _pkg("growing-tool", installs_30d=5_000, installs_90d=6_000, installs_365d=6_500),
    ]
    opts = SearchOptions(query=[], sort="trending")
    result = rank(local, opts)
    assert result[0].name == "growing-tool"


def test_rank_by_trending_sorts_unknown_trend_last():
    local = [
        _pkg("no-history", installs_30d=100, installs_90d=-1, installs_365d=-1),
        _pkg("has-history", installs_30d=100, installs_90d=50, installs_365d=200),
    ]
    opts = SearchOptions(query=[], sort="trending")
    result = rank(local, opts)
    assert result[-1].name == "no-history"


def test_default_search_options_sort_is_installs_90d():
    assert SearchOptions().sort == "installs_90d"


def test_rank_by_90d():
    local = [
        _pkg("rare-json",      installs_90d=500),
        _pkg("popular-parser", installs_90d=900_000),
        _pkg("medium-json",    installs_90d=50_000),
    ]
    opts = SearchOptions(query=[], sort="installs_90d")
    result = rank(local, opts)
    assert result[0].name == "popular-parser"


def test_rank_keeps_exact_match_first_then_uses_installs():
    local = [
        _pkg("json", installs_30d=20, desc="exact match"),
        _pkg("rare-json", installs_30d=100, desc="json tool"),
        _pkg("popular-parser", installs_30d=900_000, desc="json parser"),
        _pkg("medium-json", installs_30d=50_000, desc="json name match"),
    ]
    opts = SearchOptions(query=["json"], sort="installs_30d")
    result = rank(local, opts)
    assert [p.name for p in result] == [
        "json",
        "popular-parser",
        "medium-json",
        "rare-json",
    ]


def test_rank_popular_description_match_can_beat_weaker_name_match():
    local = [
        _pkg("git-small", installs_30d=100, desc="git helper"),
        _pkg("gh", installs_30d=282_000, desc="GitHub command-line tool"),
    ]
    opts = SearchOptions(query=["git"], sort="installs_30d")
    result = rank(local, opts)
    assert [p.name for p in result] == ["gh", "git-small"]


def test_rank_by_name():
    opts = SearchOptions(query=["ripgrep"], sort="name")
    result = rank(list(pkgs), opts)
    names = [p.name for p in result]
    assert names == sorted(names)


def test_rank_no_match():
    opts = SearchOptions(query=["not-present"])
    result = rank(list(pkgs), opts)
    assert result == []


def test_rank_name_search_uses_formula_aliases():
    local = [_pkg("ripgrep", aliases=["rg"])]
    opts = SearchOptions(query=["rg"])
    result = rank(local, opts)
    assert [p.name for p in result] == ["ripgrep"]


def test_rank_name_search_simplifies_like_brew():
    local = [_pkg("with-dashes")]
    opts = SearchOptions(query=["with dashes"])
    result = rank(local, opts)
    assert [p.name for p in result] == ["with-dashes"]


def test_rank_name_search_includes_formula_fuzzy_matches():
    local = [
        _pkg("zmap", installs_30d=100),
        _pkg("nmap", installs_30d=200),
        _pkg("zenmap", type_="cask", installs_30d=10),
    ]
    opts = SearchOptions(query=["zenmap"])
    result = rank(local, opts)
    assert {p.name for p in result} == {"zmap", "nmap", "zenmap"}


def test_rank_name_search_avoids_loose_formula_fuzzy_matches():
    local = [
        _pkg("unshield", installs_30d=117),
        _pkg("font-sunshiney", type_="cask", installs_30d=60),
    ]
    opts = SearchOptions(query=["sunshine"])
    result = rank(local, opts)
    assert [p.name for p in result] == ["font-sunshiney"]


def test_rank_name_search_orders_name_matches_before_fuzzy_popularity():
    local = [
        _pkg("zmap", installs_30d=100_000),
        _pkg("zenmap", type_="cask", installs_30d=10),
    ]
    opts = SearchOptions(query=["zenmap"])
    result = rank(local, opts)
    assert [p.name for p in result] == ["zenmap", "zmap"]


def test_rank_name_search_spell_corrects_casks_like_brew():
    local = [_pkg("zenmap", type_="cask")]
    opts = SearchOptions(query=["zmap"])
    result = rank(local, opts)
    assert [p.name for p in result] == ["zenmap"]


def test_rank_regex_query_matches_names_and_descriptions():
    import re

    local = [_pkg("ripgrep", desc="Fast line search"), _pkg("bat"), _pkg("rg-ish")]
    opts = SearchOptions(query=["/^r.*h?$/"], regex=re.compile("^r.*h?$"))
    result = rank(local, opts)
    assert {p.name for p in result} == {"ripgrep", "rg-ish"}


def test_rank_deprecated_included_with_no_limit():
    deprecated = _pkg("old-tool", installs_30d=999_999, deprecated=True)
    local = list(pkgs) + [deprecated]
    opts = SearchOptions(query=[], sort="installs_30d", limit=0)
    result = rank(local, opts)
    assert any(p.name == "old-tool" for p in result)


def test_rank_deprecated_excluded_when_results_overflow_view():
    deprecated = _pkg("old-tool", installs_30d=999_999, deprecated=True)
    local = list(pkgs) + [deprecated]  # 6 total
    opts = SearchOptions(query=[], sort="installs_30d", limit=5)  # limit < total
    result = rank(local, opts)
    assert all(p.name != "old-tool" for p in result)


def test_rank_deprecated_included_when_results_fit_in_view():
    deprecated = _pkg("old-tool", installs_30d=999_999, deprecated=True)
    local = list(pkgs) + [deprecated]  # 6 total
    opts = SearchOptions(query=[], sort="installs_30d", limit=10)  # limit > total
    result = rank(local, opts)
    assert any(p.name == "old-tool" for p in result)


def test_rank_deprecated_last_with_show_all():
    deprecated = _pkg("old-tool", installs_30d=999_999, deprecated=True)
    local = list(pkgs) + [deprecated]
    opts = SearchOptions(query=[], sort="installs_30d", show_all=True, limit=0)
    result = rank(local, opts)
    assert result[-1].name == "old-tool"


def test_rank_disabled_included_with_no_limit():
    disabled = _pkg("dead-tool", installs_30d=999_999, disabled=True)
    local = list(pkgs) + [disabled]
    opts = SearchOptions(query=[], sort="installs_30d", limit=0)
    result = rank(local, opts)
    assert any(p.name == "dead-tool" for p in result)


def test_rank_installed_only_filter():
    local = [
        _pkg("installed-tool", installed=True, installs_30d=1_000),
        _pkg("other-tool", installed=False, installs_30d=5_000),
    ]
    opts = SearchOptions(query=[], installed_only=True)
    result = rank(local, opts)
    assert [p.name for p in result] == ["installed-tool"]


def test_rank_installed_sorts_by_type_then_name():
    installed = [_pkg("zzz"), _pkg("aaa"), _pkg("mid-cask", type_="cask")]
    opts = ListOptions()
    result = rank_installed(installed, opts)
    types = [p.type for p in result]
    assert types == sorted(types)


# --- build_search_options limit precedence ---

def _args(**kwargs):
    defaults = {"query": [], "sort": None, "top": None, "columns": None, "verbose": False, "tsv": False, "installed": False}
    return argparse.Namespace(**{**defaults, **kwargs})


def _cfg(limit=0):
    return {"search": {"sort": "installs_30d"}, "output": {"limit": limit, "columns": []}}


def test_build_search_options_non_tty_has_no_limit():
    opts = build_search_options(_args(query=["git"]), _cfg(), tty_rows=None)
    assert opts.limit == 0


def test_build_search_options_tty_uses_terminal_height():
    opts = build_search_options(_args(query=["git"]), _cfg(), tty_rows=24)
    assert opts.limit == 18  # max(5, 24 - 6)


def test_build_search_options_tty_clamps_small_terminals():
    opts = build_search_options(_args(query=["git"]), _cfg(), tty_rows=8)
    assert opts.limit == 5  # max(5, 8 - 6)


def test_build_search_options_config_limit_overrides_tty():
    opts = build_search_options(_args(query=["git"]), _cfg(limit=20), tty_rows=24)
    assert opts.limit == 20


def test_build_search_options_top_flag_overrides_all():
    opts = build_search_options(_args(query=["git"], top=5), _cfg(limit=20), tty_rows=24)
    assert opts.limit == 5


def test_build_search_options_top_without_explicit_sort_uses_config_default():
    # --top used to hardcode "trending" regardless of config; it should now
    # just follow whatever sort is otherwise in effect.
    opts = build_search_options(_args(query=["git"], top=5), _cfg(), tty_rows=None)
    assert opts.sort == "installs_30d"
