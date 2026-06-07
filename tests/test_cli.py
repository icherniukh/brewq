from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from brewq.cli import _live_search, main
from brewq.model import Package
from brewq.options import SearchOptions


def _pkg(name: str, type_: str = "formula", installs_30d: int = 10_000) -> Package:
    return Package(
        name=name, type=type_, description=f"Description of {name}",
        url="https://example.com", version="1.0",
        installs_30d=installs_30d, installs_365d=-1,
        installed=False, deprecated=False, disabled=False,
    )


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("BREWQ_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("BREWQ_CONFIG", str(tmp_path / "config.toml"))


def test_main_no_args_prints_help(capsys):
    rc = main([])
    assert rc == 2


def test_main_search_no_cache_no_brew(capsys):
    with patch("brewq.cache.load_packages", return_value=[]), \
         patch("brewq.cache.refresh_background"), \
         patch("brewq.cli._live_search", return_value=[]):
        rc = main(["ripgrep"])
    assert rc == 0  # no results but no error
    captured = capsys.readouterr()
    assert "Cache not built" in captured.err


def test_main_search_from_cache(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000), _pkg("bat", installs_30d=50_000)]
    with patch("brewq.cache.load_packages", return_value=pkgs), \
         patch("brewq.cache.refresh_background"):
        rc = main(["ripgrep"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ripgrep" in out


def test_main_search_default_columns_omit_type(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000)]
    with patch("brewq.cache.load_packages", return_value=pkgs), \
         patch("brewq.cache.refresh_background"):
        rc = main(["ripgrep"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "TYPE" not in out
    assert "VERSION" in out
    assert "INSTALLS(30d)" in out


def test_main_search_columns_short_alias(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000)]
    with patch("brewq.cache.load_packages", return_value=pkgs), \
         patch("brewq.cache.refresh_background"):
        rc = main(["ripgrep", "-c", "name,installs"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ripgrep" in out
    assert "DESCRIPTION" not in out


def test_main_list_columns_short_alias(capsys):
    with patch("brewq.brew.info_installed", return_value={
        "formulae": [{
            "name": "ripgrep",
            "full_name": "ripgrep",
            "desc": "Search tool",
            "homepage": "https://example.com",
            "versions": {"stable": "1.0"},
        }],
        "casks": [],
    }):
        rc = main(["list", "-c", "name,version"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ripgrep" in out
    assert "DESCRIPTION" not in out


def test_main_search_desc_flag_searches_descriptions(capsys):
    pkgs = [_pkg("tmux", installs_30d=80_000)]
    with patch("brewq.cache.load_packages", return_value=pkgs), \
         patch("brewq.cache.refresh_background"):
        rc = main(["--desc", "Description"])
    assert rc == 0
    assert "tmux" in capsys.readouterr().out


def test_main_search_default_excludes_descriptions(capsys):
    pkgs = [_pkg("tmux", installs_30d=80_000)]
    with patch("brewq.cache.load_packages", return_value=pkgs), \
         patch("brewq.cache.refresh_background"):
        rc = main(["Description"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "No results" in captured.err


def test_live_search_matches_brew_default_scope():
    class Result:
        stdout = "==> Formulae\nripgrep\n"

    with patch("brewq.cli.shutil.which", return_value="/opt/homebrew/bin/brew"), \
         patch("brewq.cli.subprocess.run", return_value=Result()) as run, \
         patch("brewq.brew.info_packages", return_value={"formulae": [], "casks": []}) as info:
        _live_search(SearchOptions(query=["grep"], search_scope="name"))

    assert run.call_args.args[0] == ["/opt/homebrew/bin/brew", "search", "--", "grep"]
    assert info.call_args.args[0] == ["ripgrep"]


def test_live_search_uses_brew_desc_when_requested():
    class Result:
        stdout = "Warning: ignored\n==> Formulae\nripgrep: Search tool like grep\n"

    with patch("brewq.cli.shutil.which", return_value="/opt/homebrew/bin/brew"), \
         patch("brewq.cli.subprocess.run", return_value=Result()) as run, \
         patch("brewq.brew.info_packages", return_value={"formulae": [], "casks": []}) as info:
        _live_search(SearchOptions(query=["grep"], search_scope="all"))

    assert run.call_args.args[0] == ["/opt/homebrew/bin/brew", "search", "--desc", "--", "grep"]
    assert info.call_args.args[0] == ["ripgrep"]


def test_main_search_json(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000)]
    with patch("brewq.cache.load_packages", return_value=pkgs), \
         patch("brewq.cache.refresh_background"):
        rc = main(["ripgrep", "--json"])
    assert rc == 0
    records = json.loads(capsys.readouterr().out)
    assert records[0]["name"] == "ripgrep"


def test_main_search_bad_column(capsys):
    pkgs = [_pkg("ripgrep")]
    with patch("brewq.cache.load_packages", return_value=pkgs), \
         patch("brewq.cache.refresh_background"):
        rc = main(["ripgrep", "--columns", "bogus"])
    assert rc == 1
    assert "Unknown column" in capsys.readouterr().err


def test_main_cache_status(capsys, tmp_path):
    with patch("brewq.cache.status", return_value={
        "path": "/tmp/brewq/brew-all.json",
        "exists": True, "age_seconds": 100,
        "formula_count": 5000, "cask_count": 2000,
        "has_analytics": True, "locked": False,
    }):
        rc = main(["cache", "status"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "5000" in out
    assert "100s" in out


def test_main_cache_clear(capsys):
    with patch("brewq.cache.clear") as mock_clear:
        rc = main(["cache", "clear"])
    assert rc == 0
    mock_clear.assert_called_once()


def test_main_update_cache_alias(capsys):
    with patch("brewq.cache.refresh") as mock_refresh, \
         patch("brewq.cache.status", return_value={
             "formula_count": 1, "cask_count": 0
         }):
        main(["update-cache"])
    mock_refresh.assert_called_once()


def test_main_config_path(capsys):
    rc = main(["config", "path"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out.endswith("config.toml")


def test_main_list_no_brew(capsys):
    with patch("brewq.brew.info_installed", side_effect=FileNotFoundError("brew not found")):
        rc = main(["list"])
    assert rc == 1
    assert "brew not found" in capsys.readouterr().err
