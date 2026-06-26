from __future__ import annotations

import io
from unittest.mock import patch

import pytest

from brewq.cli import main
from brewq.model import Package


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
         patch("subprocess.run", side_effect=AssertionError("called Homebrew")):
        rc = main(["ripgrep"])
    assert rc == 0  # no results but no error
    captured = capsys.readouterr()
    assert "Cache not built" in captured.err


def test_main_search_from_cache(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000), _pkg("bat", installs_30d=50_000)]
    with patch("brewq.cache.load_packages", return_value=pkgs), \
         patch("brewq.cache.age_seconds", return_value=90), \
         patch("subprocess.run", side_effect=AssertionError("called Homebrew")):
        rc = main(["ripgrep"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "ripgrep" in captured.out
    assert "cache: 1m old" in captured.err


def test_main_search_defaults_to_top_15(capsys):
    pkgs = [
        _pkg(f"git-tool-{i:02d}", installs_30d=10_000 - i)
        for i in range(45)
    ]
    with patch("brewq.cache.load_packages", return_value=pkgs):
        rc = main(["git"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "git-tool-14" in out
    assert "git-tool-15" not in out
    assert "git-tool-44" not in out


def test_main_search_explicit_top_overrides_default(capsys):
    pkgs = [
        _pkg(f"git-tool-{i:02d}", installs_30d=10_000 - i)
        for i in range(20)
    ]
    with patch("brewq.cache.load_packages", return_value=pkgs):
        rc = main(["-t", "10", "git"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "git-tool-09" in out
    assert "git-tool-10" not in out


def test_main_search_default_columns_omit_type(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000)]
    with patch("brewq.cache.load_packages", return_value=pkgs):
        rc = main(["ripgrep"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "TYPE" not in out
    assert "30d" in out


def test_main_search_columns_short_alias(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000)]
    with patch("brewq.cache.load_packages", return_value=pkgs):
        rc = main(["ripgrep", "-c", "name,installs"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ripgrep" in out
    assert "DESCRIPTION" not in out


def test_main_search_explicit_30d_alias(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000)]
    with patch("brewq.cache.load_packages", return_value=pkgs):
        rc = main(["ripgrep", "-c", "name,30d"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "30d" in out


def test_main_search_explicit_365d_alias(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000)]
    with patch("brewq.cache.load_packages", return_value=pkgs):
        rc = main(["ripgrep", "-c", "name,365d"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "365d" in out


def test_main_search_preset_compact(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000)]
    with patch("brewq.cache.load_packages", return_value=pkgs):
        rc = main(["ripgrep", "-p", "compact"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ripgrep" in out
    assert "VERSION" not in out


def test_main_search_preset_and_columns_error(capsys):
    pkgs = [_pkg("ripgrep")]
    with patch("brewq.cache.load_packages", return_value=pkgs):
        rc = main(["ripgrep", "-p", "compact", "-c", "name,30d"])
    assert rc == 1
    assert "cannot use both" in capsys.readouterr().err


def test_main_search_sort_by_name(capsys):
    pkgs = [_pkg("zzz", installs_30d=99_999), _pkg("aaa", installs_30d=1)]
    with patch("brewq.cache.load_packages", return_value=pkgs):
        rc = main(["aaa", "-s", "name"])
    assert rc == 0


def test_main_search_sort_alias_n(capsys):
    pkgs = [_pkg("zzz", installs_30d=99_999), _pkg("aaa", installs_30d=1)]
    with patch("brewq.cache.load_packages", return_value=pkgs):
        rc = main(["aaa", "-s", "n"])
    assert rc == 0


def test_main_search_sort_invalid(capsys):
    pkgs = [_pkg("ripgrep")]
    with patch("brewq.cache.load_packages", return_value=pkgs):
        rc = main(["ripgrep", "-s", "bogus"])
    assert rc == 1
    assert "Unknown sort field" in capsys.readouterr().err


def test_main_search_installed_filter(capsys):
    pkgs = [
        _pkg("installed-tool", installed=True, installs_30d=1_000),
        _pkg("other-tool", installed=False, installs_30d=5_000),
    ]
    with patch("brewq.cache.load_packages", return_value=pkgs):
        rc = main(["-l", "installed-tool"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "installed-tool" in out
    assert "other-tool" not in out


def test_main_search_discloses_stale_cache(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000)]
    with patch("brewq.cache.load_packages", return_value=pkgs), \
         patch("brewq.cache.age_seconds", return_value=90_000):
        rc = main(["ripgrep"])
    assert rc == 0
    assert "cache: stale, 25h old" in capsys.readouterr().err


def test_main_list_columns_short_alias(capsys):
    with patch("brewq.cache.load_packages", return_value=[
        _pkg("ripgrep", installed=True),
    ]):
        rc = main(["list", "-c", "name,version"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ripgrep" in out
    assert "DESCRIPTION" not in out


def test_main_list_preset_compact_uses_list_shaped_profile(capsys):
    with patch("brewq.cache.load_packages", return_value=[
        _pkg("ripgrep", installed=True),
    ]):
        rc = main(["list", "-p", "compact"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "TYPE" in out
    assert "30d" not in out


def test_main_list_preset_and_columns_error(capsys):
    rc = main(["list", "-p", "compact", "-c", "name,version"])
    assert rc == 1
    assert "cannot use both" in capsys.readouterr().err


def test_main_list_analytics_inserts_installs_before_description(capsys):
    with patch("brewq.cache.load_packages", return_value=[
        _pkg("ripgrep", installed=True, installs_30d=80_000),
    ]):
        rc = main(["list", "--analytics"])
    assert rc == 0
    header = next(line for line in capsys.readouterr().out.splitlines() if "NAME" in line)
    assert header.index("30d") < header.index("DESCRIPTION")


def test_main_list_analytics_respects_explicit_metric_column(capsys):
    with patch("brewq.cache.load_packages", return_value=[
        _pkg("ripgrep", installed=True, installs_30d=80_000),
    ]):
        rc = main(["list", "--analytics", "-c", "name,installs_365d,description"])
    assert rc == 0
    header = next(line for line in capsys.readouterr().out.splitlines() if "NAME" in line)
    assert "365d" in header
    assert "30d" not in header


def test_main_list_uses_cache_without_brew(capsys):
    pkgs = [
        _pkg("ripgrep", installed=True, installs_30d=80_000),
        _pkg("bat", installed=False, installs_30d=50_000),
    ]
    with patch("brewq.cache.load_packages", return_value=pkgs), \
         patch("brewq.cache.age_seconds", return_value=120), \
         patch("subprocess.run", side_effect=AssertionError("called Homebrew")):
        rc = main(["list"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "ripgrep" in captured.out
    assert "bat" not in captured.out
    assert "cache: 2m old" in captured.err


def test_main_list_does_not_inherit_search_result_limit(capsys):
    packages = [
        _pkg(f"installed-{i:02d}", installed=True)
        for i in range(20)
    ]
    with patch("brewq.cache.load_packages", return_value=packages):
        rc = main(["list", "-c", "name"])
    assert rc == 0
    assert "installed-19" in capsys.readouterr().out


def test_cache_age_disclosure_uses_metadata_only(capsys):
    with patch("brewq.cache.age_seconds", return_value=90), \
         patch("brewq.cache.status", side_effect=AssertionError("parsed full cache")), \
         patch("brewq.cache.load_packages", return_value=[_pkg("ripgrep")]):
        rc = main(["ripgrep"])
    assert rc == 0
    assert "cache: 1m old" in capsys.readouterr().err


def test_search_terms_after_noncommand_are_not_rerouted(capsys):
    pkgs = [_pkg("cachelib", installs_30d=80_000)]
    with patch("brewq.cache.load_packages", return_value=pkgs):
        rc = main(["cachelib", "cache"])
    assert rc == 0
    assert "cachelib" in capsys.readouterr().out


def test_main_search_matches_descriptions(capsys):
    pkgs = [_pkg("tmux", installs_30d=80_000)]
    with patch("brewq.cache.load_packages", return_value=pkgs):
        rc = main(["Description"])
    assert rc == 0
    assert "tmux" in capsys.readouterr().out


def test_main_search_without_match_reports_no_results(capsys):
    pkgs = [_pkg("tmux", installs_30d=80_000)]
    with patch("brewq.cache.load_packages", return_value=pkgs):
        rc = main(["does-not-match"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "No results" in captured.err


def test_main_search_does_not_fetch_tapped_cache_misses(capsys):
    cached = [_pkg("font-sunshiney", type_="cask", installs_30d=60)]
    with patch("brewq.cache.load_packages", return_value=cached), \
         patch("subprocess.run", side_effect=AssertionError("called Homebrew")):
        rc = main(["sunshine"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "font-sunshiney" in out
    assert "lizardbyte/homebrew/sunshine" not in out
    assert "unshield" not in out


def test_main_search_tsv(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000)]
    with patch("brewq.cache.load_packages", return_value=pkgs):
        rc = main(["ripgrep", "--tsv", "-c", "name,installs,installed"])
    assert rc == 0
    assert capsys.readouterr().out == "ripgrep\t80000\tfalse\n"


def test_main_search_passes_selected_color_scheme(capsys):
    with patch("brewq.cache.load_packages", return_value=[_pkg("ripgrep")]), \
         patch("brewq.render.render_table") as render:
        rc = main(["--colors", "9", "ripgrep"])
    assert rc == 0
    assert render.call_args.kwargs["color_scheme"] == 9


def test_main_list_passes_selected_color_scheme(capsys):
    with patch("brewq.cache.load_packages", return_value=[
        _pkg("ripgrep", installed=True),
    ]), patch("brewq.render.render_table") as render:
        rc = main(["list", "--colors", "1"])
    assert rc == 0
    assert render.call_args.kwargs["color_scheme"] == 1


@pytest.mark.parametrize("value", ["-1", "10", "nope"])
def test_main_rejects_invalid_color_scheme(value):
    with pytest.raises(SystemExit) as exc:
        main(["--colors", value, "ripgrep"])
    assert exc.value.code == 2


def test_main_list_rejects_invalid_color_scheme():
    with pytest.raises(SystemExit) as exc:
        main(["list", "--colors", "10"])
    assert exc.value.code == 2


def test_main_tsv_accepts_color_scheme_without_ansi(capsys):
    with patch("brewq.cache.load_packages", return_value=[_pkg("ripgrep")]):
        rc = main(["--colors", "9", "--tsv", "-c", "name", "ripgrep"])
    assert rc == 0
    assert capsys.readouterr().out == "ripgrep\n"


def test_stale_cache_warning_respects_no_color(monkeypatch):
    stderr = io.StringIO()
    stderr.isatty = lambda: True
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr("brewq.cli.sys.stderr", stderr)
    with patch("brewq.cache.age_seconds", return_value=90_000), \
         patch("brewq.cache.load_packages", return_value=[_pkg("ripgrep")]):
        rc = main(["ripgrep"])
    assert rc == 0
    assert "cache: stale" in stderr.getvalue()
    assert "\033[" not in stderr.getvalue()


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
    assert "Commands: list  refresh  config" in out


def test_root_help_marks_color_selector_as_temporary(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--colors" in out
    assert "temporary" in out.lower()
    assert "0..9" in out


def test_root_help_shows_sort_fields(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "Sort by: 30d (i30), 90d (i90), 365d (i365), name" in out


def test_list_help_shows_presets_and_examples(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["list", "--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "preset" in out.lower()
    assert "compact" in out
    assert "brewq list -c name,type,version" in out


def test_refresh_help_mentions_force(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["refresh", "--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "brewq refresh --force" in out
    assert "brewq config path" in out


def test_main_search_bad_column(capsys):
    pkgs = [_pkg("ripgrep")]
    with patch("brewq.cache.load_packages", return_value=pkgs):
        rc = main(["ripgrep", "--columns", "bogus"])
    assert rc == 1
    assert "Unknown column" in capsys.readouterr().err


def test_main_refresh_command(capsys):
    with patch("brewq.cache.refresh") as mock_refresh, \
         patch("brewq.cache.status", return_value={
             "formula_count": 1, "cask_count": 0
         }):
        rc = main(["refresh"])
    assert rc == 0
    mock_refresh.assert_called_once()


def test_main_search_refresh_flag_refreshes_before_query(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000)]
    with patch("brewq.cache.refresh") as refresh, \
         patch("brewq.cache.load_packages", return_value=pkgs), \
         patch("brewq.cache.age_seconds", return_value=0):
        rc = main(["-r", "ripgrep"])
    assert rc == 0
    refresh.assert_called_once_with(force=True)
    assert "ripgrep" in capsys.readouterr().out


def test_main_config_path(capsys):
    rc = main(["config", "path"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out.endswith("config.toml")


def test_main_list_missing_cache_is_empty_and_quick(capsys):
    with patch("subprocess.run", side_effect=AssertionError("called Homebrew")):
        rc = main(["list"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "brew not found" not in captured.err
    assert "cache: missing" in captured.err
