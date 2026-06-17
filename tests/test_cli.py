from __future__ import annotations

from unittest.mock import patch

import pytest

from brewq.cli import _augment_with_live_search, _live_search, main
from brewq.model import Package
from brewq.options import SearchOptions


def _pkg(name: str, type_: str = "formula", installs_30d: int = 10_000,
         installed: bool = False) -> Package:
    return Package(
        name=name, type=type_, description=f"Description of {name}",
        url="https://example.com", version="1.0",
        installs_30d=installs_30d, installs_90d=-1, installs_365d=-1,
        installed=installed, deprecated=False, disabled=False,
    )


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("BREWQ_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("BREWQ_CONFIG", str(tmp_path / "config.toml"))


def test_main_no_args_prints_help(capsys):
    rc = main([])
    assert rc == 2
    out = capsys.readouterr().out
    assert "Commands:" in out
    assert "Examples:" in out
    assert "-s" in out


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
         patch("brewq.cache.refresh_background"), \
         patch("brewq.cli._augment_with_live_search", side_effect=lambda packages, _: packages):
        rc = main(["ripgrep"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ripgrep" in out


def test_main_search_default_columns_omit_type(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000)]
    with patch("brewq.cache.load_packages", return_value=pkgs), \
         patch("brewq.cache.refresh_background"), \
         patch("brewq.cli._augment_with_live_search", side_effect=lambda packages, _: packages):
        rc = main(["ripgrep"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "TYPE" not in out
    assert "30D" in out


def test_main_search_columns_short_alias(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000)]
    with patch("brewq.cache.load_packages", return_value=pkgs), \
         patch("brewq.cache.refresh_background"), \
         patch("brewq.cli._augment_with_live_search", side_effect=lambda packages, _: packages):
        rc = main(["ripgrep", "-c", "name,installs"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ripgrep" in out
    assert "DESCRIPTION" not in out


def test_main_search_explicit_30d_alias(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000)]
    with patch("brewq.cache.load_packages", return_value=pkgs), \
         patch("brewq.cache.refresh_background"), \
         patch("brewq.cli._augment_with_live_search", side_effect=lambda packages, _: packages):
        rc = main(["ripgrep", "-c", "name,30d"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "30D" in out


def test_main_search_explicit_365d_alias(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000)]
    with patch("brewq.cache.load_packages", return_value=pkgs), \
         patch("brewq.cache.refresh_background"), \
         patch("brewq.cli._augment_with_live_search", side_effect=lambda packages, _: packages):
        rc = main(["ripgrep", "-c", "name,365d"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "365D" in out


def test_main_search_preset_compact(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000)]
    with patch("brewq.cache.load_packages", return_value=pkgs), \
         patch("brewq.cache.refresh_background"), \
         patch("brewq.cli._augment_with_live_search", side_effect=lambda packages, _: packages):
        rc = main(["ripgrep", "-p", "compact"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ripgrep" in out
    assert "VERSION" not in out


def test_main_search_preset_and_columns_error(capsys):
    pkgs = [_pkg("ripgrep")]
    with patch("brewq.cache.load_packages", return_value=pkgs), \
         patch("brewq.cache.refresh_background"):
        rc = main(["ripgrep", "-p", "compact", "-c", "name,30d"])
    assert rc == 1
    assert "cannot use both" in capsys.readouterr().err


def test_main_search_sort_by_name(capsys):
    pkgs = [_pkg("zzz", installs_30d=99_999), _pkg("aaa", installs_30d=1)]
    with patch("brewq.cache.load_packages", return_value=pkgs), \
         patch("brewq.cache.refresh_background"), \
         patch("brewq.cli._augment_with_live_search", side_effect=lambda packages, _: packages):
        rc = main(["aaa", "-s", "name"])
    assert rc == 0


def test_main_search_sort_alias_n(capsys):
    pkgs = [_pkg("zzz", installs_30d=99_999), _pkg("aaa", installs_30d=1)]
    with patch("brewq.cache.load_packages", return_value=pkgs), \
         patch("brewq.cache.refresh_background"), \
         patch("brewq.cli._augment_with_live_search", side_effect=lambda packages, _: packages):
        rc = main(["aaa", "-s", "n"])
    assert rc == 0


def test_main_search_sort_invalid(capsys):
    pkgs = [_pkg("ripgrep")]
    with patch("brewq.cache.load_packages", return_value=pkgs), \
         patch("brewq.cache.refresh_background"):
        rc = main(["ripgrep", "-s", "bogus"])
    assert rc == 1
    assert "Unknown sort field" in capsys.readouterr().err


def test_main_search_installed_filter(capsys):
    pkgs = [
        _pkg("installed-tool", installed=True, installs_30d=1_000),
        _pkg("other-tool", installed=False, installs_30d=5_000),
    ]
    with patch("brewq.cache.load_packages", return_value=pkgs), \
         patch("brewq.cache.refresh_background"), \
         patch("brewq.cli._augment_with_live_search", side_effect=lambda packages, _: packages):
        rc = main(["-l", "installed-tool"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "installed-tool" in out
    assert "other-tool" not in out


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


def test_main_list_preset_compact_uses_list_shaped_profile(capsys):
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
        rc = main(["list", "-p", "compact"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "TYPE" in out
    assert "30D" not in out


def test_main_list_preset_and_columns_error(capsys):
    with patch("brewq.brew.info_installed", return_value={"formulae": [], "casks": []}):
        rc = main(["list", "-p", "compact", "-c", "name,version"])
    assert rc == 1
    assert "cannot use both" in capsys.readouterr().err


def test_main_list_analytics_inserts_installs_before_description(capsys):
    with patch("brewq.brew.info_installed", return_value={
        "formulae": [{
            "name": "ripgrep",
            "full_name": "ripgrep",
            "desc": "Search tool",
            "homepage": "https://example.com",
            "versions": {"stable": "1.0"},
        }],
        "casks": [],
    }), patch("brewq.cache.load_packages", return_value=[_pkg("ripgrep", installs_30d=80_000)]):
        rc = main(["list", "--analytics"])
    assert rc == 0
    header = next(line for line in capsys.readouterr().out.splitlines() if "NAME" in line)
    assert header.index("30D") < header.index("DESCRIPTION")


def test_main_list_analytics_respects_explicit_metric_column(capsys):
    with patch("brewq.brew.info_installed", return_value={
        "formulae": [{
            "name": "ripgrep",
            "full_name": "ripgrep",
            "desc": "Search tool",
            "homepage": "https://example.com",
            "versions": {"stable": "1.0"},
        }],
        "casks": [],
    }), patch("brewq.cache.load_packages", return_value=[_pkg("ripgrep", installs_30d=80_000)]):
        rc = main(["list", "--analytics", "-c", "name,installs_365d,description"])
    assert rc == 0
    header = next(line for line in capsys.readouterr().out.splitlines() if "NAME" in line)
    assert "365D" in header
    assert "30D" not in header


def test_search_terms_after_noncommand_are_not_rerouted(capsys):
    pkgs = [_pkg("cachelib", installs_30d=80_000)]
    with patch("brewq.cache.load_packages", return_value=pkgs), \
         patch("brewq.cache.refresh_background"), \
         patch("brewq.cli._augment_with_live_search", side_effect=lambda packages, _: packages):
        rc = main(["cachelib", "cache"])
    assert rc == 0
    assert "cachelib" in capsys.readouterr().out


def test_main_search_matches_descriptions(capsys):
    pkgs = [_pkg("tmux", installs_30d=80_000)]
    with patch("brewq.cache.load_packages", return_value=pkgs), \
         patch("brewq.cache.refresh_background"), \
         patch("brewq.cli._augment_with_live_search", side_effect=lambda packages, _: packages):
        rc = main(["Description"])
    assert rc == 0
    assert "tmux" in capsys.readouterr().out


def test_main_search_without_match_reports_no_results(capsys):
    pkgs = [_pkg("tmux", installs_30d=80_000)]
    with patch("brewq.cache.load_packages", return_value=pkgs), \
         patch("brewq.cache.refresh_background"), \
         patch("brewq.cli._augment_with_live_search", side_effect=lambda packages, _: packages):
        rc = main(["does-not-match"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "No results" in captured.err


def test_live_search_matches_brew_default_scope():
    class Result:
        stdout = "==> Formulae\nripgrep\n"

    with patch("brewq.cli.shutil.which", return_value="/opt/homebrew/bin/brew"), \
         patch("brewq.cli.subprocess.run", return_value=Result()) as run, \
         patch("brewq.brew.info_packages", return_value={"formulae": [], "casks": []}) as info:
        _live_search(SearchOptions(query=["grep"]))

    assert run.call_args.args[0] == ["/opt/homebrew/bin/brew", "search", "--", "grep"]
    assert info.call_args.args[0] == ["ripgrep"]


def test_live_search_fetches_all_large_result_sets():
    names = [f"tool-{i}" for i in range(135)]

    def info_packages(batch):
        return {
            "formulae": [
                {
                    "name": name,
                    "full_name": name,
                    "desc": f"Description of {name}",
                    "homepage": "https://example.com",
                    "versions": {"stable": "1.0"},
                }
                for name in batch
            ],
            "casks": [],
        }

    with patch("brewq.cli._brew_search_names", return_value=names), \
         patch("brewq.brew.info_packages", side_effect=info_packages) as info:
        packages = _live_search(SearchOptions(query=["tool"]))

    assert len(packages) == len(names)
    assert [len(call.args[0]) for call in info.call_args_list] == [100, 35]


def test_augment_with_live_search_fetches_tapped_cache_misses():
    cached = [_pkg("font-sunshiney", type_="cask", installs_30d=60)]
    with patch(
        "brewq.cli._brew_search_names",
        return_value=["lizardbyte/homebrew/sunshine", "font-sunshiney"],
    ), patch(
        "brewq.brew.info_packages",
        return_value={
            "formulae": [{
                "name": "sunshine",
                "full_name": "lizardbyte/homebrew/sunshine",
                "desc": "Self-hosted game stream host",
                "homepage": "https://app.lizardbyte.dev/Sunshine/",
                "versions": {"stable": "2025.122.141614"},
            }],
            "casks": [],
        },
    ) as info:
        packages = _augment_with_live_search(cached, SearchOptions(query=["sunshine"]))

    assert [p.name for p in packages] == ["font-sunshiney", "lizardbyte/homebrew/sunshine"]
    assert info.call_args.args[0] == ["lizardbyte/homebrew/sunshine"]


def test_main_search_includes_tapped_live_cache_miss(capsys):
    cached = [_pkg("font-sunshiney", type_="cask", installs_30d=60)]
    tapped = _pkg("lizardbyte/homebrew/sunshine", installs_30d=-1)
    with patch("brewq.cache.load_packages", return_value=cached), \
         patch("brewq.cache.refresh_background"), \
         patch("brewq.cli._augment_with_live_search", return_value=[*cached, tapped]):
        rc = main(["sunshine"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "font-sunshiney" in out
    assert "lizardbyte/homebrew/sunshine" in out
    assert "unshield" not in out


def test_main_search_tsv(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000)]
    with patch("brewq.cache.load_packages", return_value=pkgs), \
         patch("brewq.cache.refresh_background"), \
         patch("brewq.cli._augment_with_live_search", side_effect=lambda packages, _: packages):
        rc = main(["ripgrep", "--tsv", "-c", "name,installs,installed"])
    assert rc == 0
    assert capsys.readouterr().out == "ripgrep\t80000\tfalse\n"


def test_random_runs_generated_search(capsys):
    with patch("brewq.cli._cmd_search", return_value=0) as search:
        rc = main(["random", "--seed", "7"])
    assert rc == 0
    generated = capsys.readouterr().err.strip()
    assert generated.startswith("brewq -t ")
    args = search.call_args.args[0]
    assert args.query
    assert args.sort in {"30d", "90d", "365d", "name"}
    assert not args.tsv


def test_root_help_mentions_tsv_and_discoverability(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--tsv" in out
    assert "Commands: list  cache  config" in out


def test_root_help_shows_sort_fields(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "Sort by:" in out
    assert "30d" in out
    assert "365d" in out


def test_list_help_shows_presets_and_examples(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["list", "--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "preset" in out.lower()
    assert "compact" in out
    assert "brewq list -c name,type,version" in out


def test_cache_help_mentions_refresh_flow(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["cache", "--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "brewq cache refresh --force" in out
    assert "brewq config path" in out


def test_main_search_bad_column(capsys):
    pkgs = [_pkg("ripgrep")]
    with patch("brewq.cache.load_packages", return_value=pkgs), \
         patch("brewq.cache.refresh_background"), \
         patch("brewq.cli._augment_with_live_search", side_effect=lambda packages, _: packages):
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
