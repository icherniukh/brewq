from __future__ import annotations

import argparse
import os

import pytest

from brewq.model import Package
from brewq.options import (
    SearchOptions,
    build_search_options,
    parse_sort,
    rank,
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

@pytest.mark.parametrize("name", ["30d", "90d", "365d", "trend", "name"])
def test_parse_sort_exact(name):
    assert parse_sort(name) == name


@pytest.mark.parametrize("old", [
    "installs_30d", "installs_90d", "installs_365d",
    "30", "i30", "installs", "install",
    "90", "i90", "default",
    "365", "i365", "year", "y", "annual",
    "trending", "hot", "n", "nm",
    "alpha", "alphabetical", "az", "a-z",
    " YEAR ",
])
def test_old_sort_names_are_unknown(old):
    with pytest.raises(ValueError, match="Unknown sort field"):
        parse_sort(old)


@pytest.mark.parametrize("typo,expected", [("trned", "trend"), ("NAME", "name"), ("30D", "30d")])
def test_sort_typos_suggest_without_resolving(typo, expected):
    with pytest.raises(ValueError, match=f"Did you mean {expected!r}"):
        parse_sort(typo)


def test_parse_sort_unknown_raises():
    with pytest.raises(ValueError, match="Unknown sort field") as error:
        parse_sort("bogus")
    assert str(error.value).endswith("Valid: 90d, 30d, 365d, trend, name")


# --- rank ---

def test_rank_by_installs_30d():
    opts = SearchOptions(query=["ripgrep"], sort="30d")
    result = rank(list(pkgs), opts)
    assert result[0].name == "ripgrep"


def test_rank_by_trending_prefers_higher_trend_score():
    local = [
        _pkg("declining-tool", installs_30d=50, installs_90d=600, installs_365d=3_000),
        _pkg("growing-tool", installs_30d=5_000, installs_90d=6_000, installs_365d=6_500),
    ]
    opts = SearchOptions(query=[], sort="trend")
    result = rank(local, opts)
    assert result[0].name == "growing-tool"


def test_rank_by_trending_sorts_unknown_trend_last():
    local = [
        _pkg("no-history", installs_30d=100, installs_90d=-1, installs_365d=-1),
        _pkg("has-history", installs_30d=100, installs_90d=50, installs_365d=200),
    ]
    opts = SearchOptions(query=[], sort="trend")
    result = rank(local, opts)
    assert result[-1].name == "no-history"


def test_default_search_options_sort_is_installs_90d():
    assert SearchOptions().sort == "90d"


def test_rank_by_90d():
    local = [
        _pkg("rare-json",      installs_90d=500),
        _pkg("popular-parser", installs_90d=900_000),
        _pkg("medium-json",    installs_90d=50_000),
    ]
    opts = SearchOptions(query=[], sort="90d")
    result = rank(local, opts)
    assert result[0].name == "popular-parser"


def test_rank_keeps_exact_match_first_then_uses_installs():
    local = [
        _pkg("json", installs_30d=20, desc="exact match"),
        _pkg("rare-json", installs_30d=100, desc="json tool"),
        _pkg("popular-parser", installs_30d=900_000, desc="json parser"),
        _pkg("medium-json", installs_30d=50_000, desc="json name match"),
    ]
    opts = SearchOptions(query=["json"], sort="30d")
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
    opts = SearchOptions(query=["git"], sort="30d")
    result = rank(local, opts)
    assert [p.name for p in result] == ["gh", "git-small"]


def test_rank_reverse_flips_after_the_cap():
    local = [_pkg("low", installs_90d=1), _pkg("high", installs_90d=9), _pkg("mid", installs_90d=5)]
    opts = SearchOptions(query=[], sort="90d", top=2, reverse=True)
    assert [pkg.name for pkg in rank(local, opts)] == ["mid", "high"]


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


def test_rank_deprecated_included_with_no_top():
    deprecated = _pkg("old-tool", installs_30d=999_999, deprecated=True)
    local = list(pkgs) + [deprecated]
    opts = SearchOptions(query=[], sort="30d", top=0)
    result = rank(local, opts)
    assert any(p.name == "old-tool" for p in result)


def test_rank_cap_counts_inactive_matches():
    deprecated = _pkg("old-tool", installs_30d=999_999, deprecated=True)
    local = list(pkgs) + [deprecated]  # 6 total
    opts = SearchOptions(query=[], sort="30d", top=5)  # top < total
    result = rank(local, opts)
    assert all(p.name != "old-tool" for p in result)
    assert opts.eligible_total == 6


def test_rank_deprecated_included_when_results_fit_in_view():
    deprecated = _pkg("old-tool", installs_30d=999_999, deprecated=True)
    local = list(pkgs) + [deprecated]  # 6 total
    opts = SearchOptions(query=[], sort="30d", top=10)  # top > total
    result = rank(local, opts)
    assert any(p.name == "old-tool" for p in result)


def test_rank_deprecated_last():
    deprecated = _pkg("old-tool", installs_30d=999_999, deprecated=True)
    local = list(pkgs) + [deprecated]
    opts = SearchOptions(query=[], sort="30d", top=0)
    result = rank(local, opts)
    assert result[-1].name == "old-tool"


def test_rank_disabled_included_with_no_top():
    disabled = _pkg("dead-tool", installs_30d=999_999, disabled=True)
    local = list(pkgs) + [disabled]
    opts = SearchOptions(query=[], sort="30d", top=0)
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


# --- build_search_options top precedence ---

def _args(**kwargs):
    defaults = {"query": [], "sort": None, "top": None, "columns": None, "tsv": False, "installed": False}
    return argparse.Namespace(**{**defaults, **kwargs})


def _cfg(top="auto"):
    return {"search": {"sort": "30d"}, "output": {"top": top, "columns": []}}


def test_build_search_options_has_no_implicit_pipe_top():
    assert build_search_options(_args(query=["git"]), _cfg()).top == 0


def test_build_search_options_config_top_applies_on_terminal(monkeypatch):
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    assert build_search_options(_args(query=["git"]), _cfg(top=20)).top == 20


@pytest.mark.parametrize("rows", [16, 26, 30])
def test_auto_cap_reserves_all_eight_non_record_lines(monkeypatch, rows):
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setattr("brewq.options.terminal_size", lambda: os.terminal_size((100, rows)))
    assert build_search_options(_args(), _cfg()).top == rows - 8


@pytest.mark.parametrize("tty,tsv", [(False, False), (False, True), (True, True)])
@pytest.mark.parametrize("all_matches", [False, True])
def test_machine_output_ignores_configured_cap_and_reverse(monkeypatch, tty, tsv, all_matches):
    monkeypatch.setattr("sys.stdout.isatty", lambda: tty)
    cfg = _cfg(top=2)
    cfg["search"]["reverse"] = True
    opts = build_search_options(_args(tsv=tsv, **{"all": all_matches}), cfg)
    assert (opts.top, opts.reverse) == (0, False)
    opts = build_search_options(_args(tsv=tsv, top=1, reverse=True), cfg)
    assert (opts.top, opts.reverse) == (1, True)


@pytest.mark.parametrize("explicit,expected", [(None, True), (False, False), (True, True)])
def test_all_removes_terminal_cap_and_defaults_to_reverse(monkeypatch, explicit, expected):
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.delenv("BREWQ_NO_REVERSE", raising=False)
    opts = build_search_options(_args(reverse=explicit, **{"all": True}), _cfg(top=2))
    assert (opts.top, opts.reverse) == (0, expected)
    opts = build_search_options(_args(top=1, **{"all": True}), _cfg(top=2))
    assert (opts.top, opts.reverse) == (1, True)
    monkeypatch.setenv("BREWQ_NO_REVERSE", "1")
    assert not build_search_options(_args(**{"all": True}), _cfg()).reverse


@pytest.mark.parametrize("sort", ["30d", "90d", "365d", "trend", "name"])
@pytest.mark.parametrize("alias", [False, True])
@pytest.mark.parametrize("status", ["deprecated", "disabled"])
def test_inactive_exact_name_or_alias_is_pinned_before_cap(sort, alias, status):
    exact = _pkg("z-python" if alias else "python@3.9",
                 aliases=["python@3.9"] if alias else [], **{status: True})
    local = [_pkg("a-python", installs_90d=999_999, desc="python@3.9"), exact]
    opts = SearchOptions(query=["python@3.9"], sort=sort, top=1)
    assert rank(local, opts) == [exact]
    assert opts.eligible_total == 2


def test_build_search_options_top_flag_overrides_config():
    opts = build_search_options(_args(query=["git"], top=5), _cfg(top=20))
    assert opts.top == 5


def test_build_search_options_top_without_explicit_sort_uses_config_default():
    # --top used to hardcode "trend" regardless of config; it should now
    # just follow whatever sort is otherwise in effect.
    opts = build_search_options(_args(query=["git"], top=5), _cfg())
    assert opts.sort == "30d"


@pytest.mark.parametrize("tty,tsv,top,all_matches,configured,auto", [
    (True, False, None, False, "auto", True),
    (False, False, None, False, "auto", False),
    (True, True, None, False, "auto", False),
    (True, False, 2, False, "auto", False),
    (True, False, None, True, "auto", False),
    (True, False, None, False, 2, False),
    (True, False, None, False, 0, False),
])
def test_vertical_height_budget_only_for_automatic_terminal_cap(
    monkeypatch, tty, tsv, top, all_matches, configured, auto,
):
    monkeypatch.setattr("sys.stdout.isatty", lambda: tty)
    monkeypatch.setattr("brewq.options.terminal_size", lambda: os.terminal_size((110, 14)))
    opts = build_search_options(_args(tsv=tsv, top=top, **{"all": all_matches}), _cfg(configured))
    assert opts.auto_height == (14 if auto else None)
