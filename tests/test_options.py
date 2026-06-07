from __future__ import annotations

from brewq.model import Package
from brewq.options import ListOptions, SearchOptions, rank, rank_installed


def _pkg(name: str, type_: str = "formula", installs_30d: int = -1,
         desc: str = "", deprecated: bool = False, disabled: bool = False,
         aliases: list[str] | None = None) -> Package:
    return Package(
        name=name, type=type_, description=desc, url="",
        version="1.0", installs_30d=installs_30d, installs_365d=-1,
        installed=False, deprecated=deprecated, disabled=disabled,
        aliases=aliases or [],
    )


pkgs = [
    _pkg("ripgrep", installs_30d=80_000, desc="Search tool like grep"),
    _pkg("ripgrep-all", installs_30d=10_000, desc="ripgrep variant for all file types"),
    _pkg("rg-tools", installs_30d=500, desc="Helper tools"),
    _pkg("bat", type_="formula", installs_30d=50_000, desc="Clone of cat with wings"),
    _pkg("somecask", type_="cask", installs_30d=5_000),
]


def test_rank_by_popularity_default():
    opts = SearchOptions(query=["ripgrep"], sort="popularity")
    result = rank(list(pkgs), opts)
    assert result[0].name == "ripgrep"


def test_rank_by_popularity_uses_selected_installs_metric():
    local = [
        _pkg("rare-json", installs_30d=100, desc="json tool"),
        _pkg("popular-parser", installs_30d=900_000, desc="json parser"),
        _pkg("medium-json", installs_30d=50_000, desc="json name match"),
    ]
    opts = SearchOptions(query=["json"], sort="popularity", search_scope="all")
    result = rank(local, opts)
    assert [p.name for p in result] == ["popular-parser", "medium-json", "rare-json"]


def test_rank_by_name():
    opts = SearchOptions(query=["ripgrep"], sort="name")
    result = rank(list(pkgs), opts)
    names = [p.name for p in result]
    assert names == sorted(names)


def test_rank_type_filter():
    opts = SearchOptions(query=[], pkg_type="cask")
    result = rank(list(pkgs), opts)
    assert all(p.type == "cask" for p in result)


def test_rank_name_only_no_desc():
    opts = SearchOptions(query=["Search tool"], search_scope="name")
    result = rank(list(pkgs), opts)
    assert result == []  # "search tool" not in any name


def test_rank_with_desc():
    opts = SearchOptions(query=["search"], search_scope="all")
    result = rank(list(pkgs), opts)
    assert any(p.name == "ripgrep" for p in result)


def test_rank_name_search_uses_formula_aliases():
    local = [_pkg("ripgrep", aliases=["rg"])]
    opts = SearchOptions(query=["rg"], search_scope="name")
    result = rank(local, opts)
    assert [p.name for p in result] == ["ripgrep"]


def test_rank_name_search_simplifies_like_brew():
    local = [_pkg("with-dashes")]
    opts = SearchOptions(query=["with dashes"], search_scope="name")
    result = rank(local, opts)
    assert [p.name for p in result] == ["with-dashes"]


def test_rank_name_search_includes_formula_fuzzy_matches():
    local = [
        _pkg("zmap", installs_30d=100),
        _pkg("nmap", installs_30d=200),
        _pkg("zenmap", type_="cask", installs_30d=10),
    ]
    opts = SearchOptions(query=["zenmap"], search_scope="name")
    result = rank(local, opts)
    assert {p.name for p in result} == {"zmap", "nmap", "zenmap"}


def test_rank_name_search_avoids_loose_formula_fuzzy_matches():
    local = [
        _pkg("unshield", installs_30d=117),
        _pkg("font-sunshiney", type_="cask", installs_30d=60),
    ]
    opts = SearchOptions(query=["sunshine"], search_scope="name")
    result = rank(local, opts)
    assert [p.name for p in result] == ["font-sunshiney"]


def test_rank_name_search_orders_name_matches_before_fuzzy_popularity():
    local = [
        _pkg("zmap", installs_30d=100_000),
        _pkg("zenmap", type_="cask", installs_30d=10),
    ]
    opts = SearchOptions(query=["zenmap"], search_scope="name")
    result = rank(local, opts)
    assert [p.name for p in result] == ["zenmap", "zmap"]


def test_rank_name_search_does_not_fuzzy_match_casks():
    local = [_pkg("zenmap", type_="cask")]
    opts = SearchOptions(query=["zmap"], search_scope="name")
    result = rank(local, opts)
    assert result == []


def test_rank_deprecated_last():
    deprecated = _pkg("old-tool", installs_30d=999_999, deprecated=True)
    local = list(pkgs) + [deprecated]
    opts = SearchOptions(query=[], sort="popularity")
    result = rank(local, opts)
    assert result[-1].name == "old-tool"


def test_rank_limit():
    opts = SearchOptions(query=[], limit=2)
    result = rank(list(pkgs), opts)
    assert len(result) == 2


def test_rank_installed_sorts_by_type_then_name():
    installed = [_pkg("zzz"), _pkg("aaa"), _pkg("mid-cask", type_="cask")]
    opts = ListOptions()
    result = rank_installed(installed, opts)
    assert result[0].name == "mid-cask"  # cask sorts before formula alphabetically? no:
    # type sort: cask < formula alphabetically? Let's check actual sort
    types = [p.type for p in result]
    # Should be sorted by (type, name)
    assert types == sorted(types)
