from __future__ import annotations

import pytest

from brewq.model import Package
from brewq.options import rank, SearchOptions, rank_installed, ListOptions


def _pkg(name: str, type_: str = "formula", installs_30d: int = -1,
         desc: str = "", deprecated: bool = False, disabled: bool = False) -> Package:
    return Package(
        name=name, type=type_, description=desc, url="",
        version="1.0", installs_30d=installs_30d, installs_365d=-1,
        installed=False, deprecated=deprecated, disabled=disabled,
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
    opts = SearchOptions(query=["Search tool"], include_desc=False)
    result = rank(list(pkgs), opts)
    assert result == []  # "search tool" not in any name


def test_rank_with_desc():
    opts = SearchOptions(query=["search"], include_desc=True)
    result = rank(list(pkgs), opts)
    assert any(p.name == "ripgrep" for p in result)


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
