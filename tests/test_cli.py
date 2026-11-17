from __future__ import annotations

import argparse
import io
import os
import runpy
from pathlib import Path
from unittest.mock import patch

import pytest

from brewq.cache import CacheLoad, RefreshOutcome, RefreshResult
from brewq.cli import _build_command_parser, _build_search_parser, main
from brewq.columns import CANONICAL_COLUMNS
from brewq.model import Package
from brewq.render import TableResult


def _pkg(name: str, type_: str = "formula", installs_30d: int = 10_000,
         installed: bool = False, installs_90d: int = -1, installs_365d: int = -1) -> Package:
    return Package(
        name=name, type=type_, description=f"Description of {name}",
        url="https://example.com", version="1.0",
        installs_30d=installs_30d, installs_90d=installs_90d, installs_365d=installs_365d,
        installed=installed, deprecated=False, disabled=False,
    )


def _loaded(
    packages: list[Package],
    *,
    source: str = "user",
    age: float = 0,
    analytics_complete: bool = True,
    repair_needed: bool = False,
) -> CacheLoad:
    return CacheLoad(
        source=source,
        packages=packages,
        age_seconds=age,
        analytics_complete=analytics_complete,
        repair_needed=repair_needed,
    )


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("BREWQ_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("BREWQ_CONFIG", str(tmp_path / "config.toml"))


@pytest.mark.parametrize("query", [[], [""]])
def test_main_empty_query_lists_catalog(capsys, query):
    with patch("brewq.cache.load", return_value=_loaded([_pkg("bat"), _pkg("ripgrep")])):
        assert main([*query, "--tsv", "-c", "name"]) == 0
    assert capsys.readouterr().out.splitlines() == ["bat", "ripgrep"]


def test_full_help_documents_columns_trending_and_cache(capsys):
    rc = main(["--full-help"])
    assert rc == 0
    out = capsys.readouterr().out
    column_block = out.split("columns:\n", 1)[1].split("\n\n", 1)[0]
    documented_columns = tuple(
        line.split(maxsplit=1)[0] for line in column_block.splitlines()
    )
    assert documented_columns == CANONICAL_COLUMNS
    assert "smoothed toward 1.0x" in out
    assert "bundled seed" in out
    assert "--all" in out
    assert "--refresh" not in out


@pytest.mark.parametrize("command", [[], ["-i"]])
@pytest.mark.parametrize(("argv", "removed", "replacement"), [
    (["-v"], "-v", "-c all"), (["--verbose"], "--verbose", "-c all"),
    (["--url"], "--url", "-c default,url"),
    (["-r"], "-r", "-u/--update"), (["--refresh"], "--refresh", "-u/--update"),
    (["--limit"], "--limit", "-t/--top"), (["--limit=2"], "--limit", "-t/--top"),
    (["--analytics"], "--analytics", "-c default,90d"), (["-Rr"], "-r", "-u/--update"),
    (["-vt3"], "-v", "-c all"), (["-t3", "-v"], "-v", "-c all"),
    (["json", "-r"], "-r", "-u/--update"),
])
def test_removed_options_name_replacements_before_io(command, argv, removed, replacement, capsys):
    with patch("brewq.config.load", side_effect=AssertionError("loaded config")), \
         patch("brewq.cache.load", side_effect=AssertionError("loaded cache")), \
         patch("brewq.cache.refresh", side_effect=AssertionError("updated cache")), \
         pytest.raises(SystemExit) as exc:
        main([*command, *argv])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "usage:" in captured.err
    assert f"{removed} was removed; use {replacement}" in captured.err


@pytest.mark.parametrize(("action", "guidance"), [
    ("+list", "use -i; -i -s name for the alphabetical view"),
    ("+refresh", "use +update"), ("+update-cache", "use +update"),
    ("+preload", "use +update --offline"),
    ("+random", "the layout lab is now scripts/random-layout.py in the brewq source repository"),
])
def test_removed_actions_name_replacements_before_io(action, guidance, capsys):
    with patch("brewq.config.load", side_effect=AssertionError("loaded config")), \
         patch("brewq.cache.refresh", side_effect=AssertionError("updated cache")), \
         pytest.raises(SystemExit) as exc:
        main([action])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert f"{action} was removed; {guidance}" in captured.err


def test_parsers_have_no_hidden_flags_or_actions():
    parsers = [_build_search_parser(), _build_command_parser()]
    while parsers:
        for action in parsers.pop()._actions:
            if action.option_strings:
                assert action.help != argparse.SUPPRESS
            if isinstance(action, argparse._SubParsersAction):
                assert set(action.choices) == {"+update", "+setup", "+config", "+completion"}
                assert all(choice.help != argparse.SUPPRESS for choice in action._choices_actions)
                parsers.extend(action.choices.values())


@pytest.mark.parametrize("term", ["--url", "-v"])
def test_removed_option_after_terminator_remains_a_query(capsys, term):
    with patch("brewq.cache.load", return_value=_loaded([_pkg(term)])):
        assert main(["--tsv", "-c", "name", "--", term]) == 0
    assert capsys.readouterr().out == f"{term}\n"


@pytest.mark.parametrize("command", [[], ["-i"]])
@pytest.mark.parametrize("flags,equivalent", [
    (["-c", "-url"], "name,ver,desc"),
    (["-c", "-ver"], "name,url,desc"),
    (["-c", "-desc"], "name,url,ver"),
    (["--columns", "-desc"], "name,url,ver"),
    (["-c=-url"], "name,ver,desc"),
    (["-c", "-ver,+bin"], "name,url,bin,desc"),
])
def test_leading_minus_columns_reach_migration_error(command, flags, equivalent, tmp_path, capsys):
    (tmp_path / "config.toml").write_text(
        'columns = ["name", "url", "ver", "desc"]\n'
        'installed-columns = ["name", "url", "ver", "desc"]\n'
    )
    argv = [*command, *flags, "--tsv"]
    if not command:
        argv.append("json")
    with patch("brewq.cache.load", side_effect=AssertionError("loaded cache")):
        assert main(argv) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert f"use -c {equivalent}" in captured.err
    assert "was removed; use -u" not in captured.err


@pytest.mark.parametrize("option", ["-s", "--sort", "-t", "--top"])
def test_missing_option_value_does_not_trigger_removed_flag_error(option, capsys):
    with pytest.raises(SystemExit) as exc:
        main([option, "-v", "json"])
    assert exc.value.code == 2
    error = capsys.readouterr().err
    assert "expected one argument" in error
    assert "was removed" not in error


def test_attached_column_value_is_not_checked_as_short_flags(capsys):
    with patch("brewq.cache.load", return_value=_loaded([_pkg("ripgrep")])):
        assert main(["--tsv", "-cver", "ripgrep"]) == 0
    assert capsys.readouterr().out == "1.0\n"


def test_update_offline_bypasses_refresh_and_operational_config(capsys):
    with patch("brewq.cache.preload_bundled", return_value=(Path("/cache"), 2, 3)) as preload, \
         patch("brewq.cache.refresh", side_effect=AssertionError("updated cache")), \
         patch("brewq.config.load", side_effect=AssertionError("loaded config")):
        assert main(["+update", "--offline"]) == 0
    preload.assert_called_once_with()
    assert capsys.readouterr() == ("cache: preloaded 2 formulae, 3 casks at /cache\n", "")


def test_update_offline_rejects_force_before_io():
    with patch("brewq.cache.preload_bundled", side_effect=AssertionError("wrote cache")), \
         pytest.raises(SystemExit) as exc:
        main(["+update", "--offline", "--force"])
    assert exc.value.code == 2


def test_main_search_bootstraps_when_seed_is_unavailable(capsys):
    loaded = _loaded([_pkg("ripgrep")], age=0)
    with patch("brewq.cache.load", side_effect=__import__("brewq.seed", fromlist=["SeedError"]).SeedError("missing")), \
         patch("brewq.cache.foreground_bootstrap", return_value=loaded), \
         patch("brewq.scheduler.schedule_if_needed", return_value="scheduled"):
        rc = main(["ripgrep"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "Initializing local package metadata" in captured.err
    assert "ripgrep" in captured.out


def test_main_search_from_cache(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000), _pkg("bat", installs_30d=50_000)]
    with patch("brewq.cache.load", return_value=_loaded(pkgs, age=90)), \
         patch("subprocess.run", side_effect=AssertionError("called Homebrew")):
        rc = main(["ripgrep"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "ripgrep" in captured.out
    assert "cache: 1min old" in captured.err


def test_main_search_non_tty_shows_all_results(capsys):
    pkgs = [
        _pkg(f"git-tool-{i:02d}", installs_30d=10_000 - i)
        for i in range(45)
    ]
    # capsys stdout is not a TTY, so no cap is applied
    with patch("brewq.cache.load", return_value=_loaded(pkgs)):
        rc = main(["git"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "git-tool-00" in out
    assert "git-tool-44" in out


def test_main_search_caps_to_terminal_height():
    import brewq.options as opts_mod

    pkgs = [
        _pkg(f"git-tool-{i:02d}", installs_30d=10_000 - i)
        for i in range(45)
    ]
    captured = []
    orig = opts_mod.build_search_options

    def spy(args, cfg):
        result = orig(args, cfg)
        captured.append(result)
        return result

    with patch("brewq.cache.load", return_value=_loaded(pkgs)), \
         patch("brewq.cli.sys.stdout") as mock_out, \
         patch("brewq.options.terminal_size", return_value=os.terminal_size((100, 26))), \
         patch("brewq.options.build_search_options", side_effect=spy):
        mock_out.isatty.return_value = True
        main(["git"])

    assert captured, "build_search_options was not called"
    assert captured[0].limit == 18


def test_main_search_explicit_top_overrides_default(capsys):
    pkgs = [
        _pkg(f"git-tool-{i:02d}", installs_30d=10_000 - i)
        for i in range(20)
    ]
    with patch("brewq.cache.load", return_value=_loaded(pkgs)):
        rc = main(["-t", "10", "git"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "git-tool-09" in out
    assert "git-tool-10" not in out


@pytest.mark.parametrize("command", [[], ["-i"]])
@pytest.mark.parametrize("flag", ["-t", "--top"])
@pytest.mark.parametrize("value", ["0", "-1", "nope", "1.5"])
def test_main_rejects_invalid_row_limits(command, flag, value):
    with pytest.raises(SystemExit) as exc:
        main([*command, flag, value])
    assert exc.value.code == 2


@pytest.mark.parametrize("command", [[], ["-i"]])
@pytest.mark.parametrize("flag", ["-t", "--top"])
@pytest.mark.parametrize("tsv", [False, True])
def test_main_limit_spellings_cap_search_and_list(command, flag, tsv, capsys):
    packages = [_pkg(f"tool-{i}", installed=True) for i in range(5)]
    args = [*command, flag, "2", "-c", "name"]
    if tsv:
        args.append("--tsv")
    if not command:
        args.extend(["--all", "tool"])
    with patch("brewq.cache.load", return_value=_loaded(packages)):
        assert main(args) == 0
    output = capsys.readouterr().out
    if tsv:
        assert output.splitlines() == ["tool-0", "tool-1"]
    else:
        assert "tool-0" in output and "tool-1" in output
        assert "tool-2" not in output


def test_main_search_default_columns_omit_type(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000, installs_90d=240_000, installs_365d=600_000)]
    with patch("brewq.cache.load", return_value=_loaded(pkgs)):
        rc = main(["ripgrep"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "TYPE" not in out
    assert "TREND" in out
    assert "90d" in out


def test_config_auto_column_picks_available_window_via_top_result(capsys, tmp_path):
    # "auto" is a config-only pseudo-column (not selectable via -c); the
    # built-in default no longer uses it now that installs_90d is a literal
    # default column, but a user can still opt into it via config.toml.
    (tmp_path / "config.toml").write_text(
        'columns = ["name", "trend", "auto", "desc"]\n'
    )
    pkg = Package(
        name="no-recent-data", type="formula", description="", url="", version="1.0",
        installs_30d=-1, installs_90d=-1, installs_365d=40_000,
        installed=False, deprecated=False, disabled=False,
    )
    with patch("brewq.cache.load", return_value=_loaded([pkg])):
        rc = main(["no-recent-data"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "TREND" not in out
    assert "365d" in out
    assert "30d" not in out
    assert "90d" not in out


@pytest.mark.parametrize("argv,expected", [
    (["ripgrep", "-c", "default,ver,bin", "--tsv"], "ripgrep\t\t\tDescription of ripgrep\t1.0\t\n"),
    (["ripgrep", "-c", "name,90d,url,desc", "--tsv"], "ripgrep\t\thttps://example.com\tDescription of ripgrep\n"),
    (["-i", "-c", "name,90d,trend,desc", "--tsv"], "ripgrep\t\t\tDescription of ripgrep\n"),
])
def test_exact_columns_search_and_list_tsv(capsys, argv, expected):
    with patch("brewq.cache.load", return_value=_loaded([_pkg("ripgrep", installed=True)])):
        assert main(argv) == 0
    assert capsys.readouterr().out == expected


def test_mixed_default_resolves_config_auto_after_ranking(capsys, tmp_path):
    (tmp_path / "config.toml").write_text('columns = ["auto"]\n')
    pkg = _pkg("ripgrep")
    pkg.installs_30d = -1
    pkg.installs_365d = 40_000
    with patch("brewq.cache.load", return_value=_loaded([pkg])):
        assert main(["ripgrep", "-c", "default,365d", "--tsv"]) == 0
    assert capsys.readouterr().out == "40000\n"


@pytest.mark.parametrize("spec", ["+bogus", "+auto", "+ver,", "name,bogus", ""])
def test_invalid_selection_fails_before_loading_cache(capsys, spec):
    with patch("brewq.cache.load", side_effect=AssertionError("loaded cache")):
        assert main(["ripgrep", "-c", spec]) == 1
    assert "brewq:" in capsys.readouterr().err


def test_main_search_short_field_names(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000)]
    with patch("brewq.cache.load", return_value=_loaded(pkgs)):
        rc = main(["ripgrep", "-c", "name,30d"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ripgrep" in out
    assert "DESC" not in out


def test_main_search_all_columns_shows_all_fields(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000, installs_90d=240_000, installs_365d=600_000)]
    pkgs[0].binaries = ["rg"]
    with patch("brewq.cache.load", return_value=_loaded(pkgs)):
        rc = main(["ripgrep", "-c", "all"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ripgrep" in out
    for header in (
        "TYPE", "VER", "30d", "90d", "365d", "TREND",
        "BIN", "URL",
    ):
        assert header in out


def test_main_search_rejects_explicit_auto_column(capsys):
    with patch("brewq.cache.load", return_value=_loaded([_pkg("ripgrep")])):
        rc = main(["ripgrep", "-c", "auto"])
    assert rc == 1
    assert "only available in search configuration" in capsys.readouterr().err


def test_main_search_default_expansion_adds_url(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000)]
    with patch("brewq.cache.load", return_value=_loaded(pkgs)):
        rc = main(["ripgrep", "-c", "default,url"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "URL" in out
    assert "example.com" in out and "https://" not in out


def test_reverse_puts_the_best_row_last_and_kill_switch_wins(capsys, monkeypatch):
    pkgs = [_pkg("low", installed=True), _pkg("high", installed=True)]
    with patch("brewq.cache.load", return_value=_loaded(pkgs)):
        assert main(["-i", "-c", "name", "--tsv", "-R"]) == 0
    assert capsys.readouterr().out.splitlines() == ["low", "high"]
    monkeypatch.setenv("BREWQ_NO_REVERSE", "1")
    with patch("brewq.cache.load", return_value=_loaded(pkgs)):
        assert main(["-i", "-c", "name", "--tsv", "-R"]) == 0
    assert capsys.readouterr().out.splitlines() == ["high", "low"]


def test_update_flag_and_command_update_before_search(capsys):
    pkgs = [_pkg("ripgrep")]
    with patch("brewq.cache.refresh", return_value=RefreshResult(
             RefreshOutcome.COMPLETE, Path("/cache/brew-all.json")
         )) as refresh, \
         patch("brewq.cache.load", return_value=_loaded(pkgs)), \
         patch("brewq.cache.status", return_value={"formula_count": 1, "cask_count": 0}):
        assert main(["-u", "ripgrep"]) == 0
        assert main(["+update"]) == 0
    assert refresh.call_count == 2
    err = capsys.readouterr().err
    assert "Updating register..." in err
    assert "register: updated" in err


def test_flags_between_query_terms_match_other_placements(capsys):
    pkgs = [_pkg(f"tool-{i:02d}", installs_30d=100 - i) for i in range(4)]

    def rows(argv: list[str]) -> str:
        with patch("brewq.cache.load", return_value=_loaded(pkgs)):
            assert main(argv) == 0
        return capsys.readouterr().out

    expected = rows(["-t", "2", "-c", "name", "--tsv", "to", "ol"])
    assert rows(["to", "-t", "2", "-c", "name", "--tsv", "ol"]) == expected
    assert rows(["to", "ol", "-c", "name", "--tsv", "-t", "2"]) == expected
    assert expected.splitlines() == ["tool-00", "tool-01"]


def test_intermixed_regex_and_column_list(capsys):
    pkgs = [_pkg("tool-00"), _pkg("other")]
    with patch("brewq.cache.load", return_value=_loaded(pkgs)):
        assert main(["/tool/", "-c", "default,ver", "-t", "1"]) == 0
    out = capsys.readouterr().out
    assert "tool-00" in out and "other" not in out and "VER" in out


def test_option_terminator_keeps_dash_terms_out_of_flags(capsys):
    with patch("brewq.cache.load", return_value=_loaded([_pkg("ripgrep")])):
        assert main(["--", "-t"]) == 0
    assert "No results for: -t" in capsys.readouterr().err


def test_bare_list_is_a_query_not_an_action(capsys):
    with patch("brewq.cache.load", return_value=_loaded([_pkg("list", installed=True), _pkg("other")])):
        assert main(["-c", "name", "--tsv", "list"]) == 0
    assert capsys.readouterr().out.strip() == "list"


def test_invalid_action_flag_shows_action_help_and_a_separated_error(capsys, monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    with pytest.raises(SystemExit) as exc:
        main(["+update", "-i"])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "usage: brewq +update" in captured.err
    assert "\n\nError: unrecognized arguments: -i" in captured.err
    assert "\033" not in captured.err


def test_first_token_still_selects_a_command(capsys):
    with patch("brewq.cache.refresh") as refresh, \
         patch("brewq.cache.status", return_value={"formula_count": 1, "cask_count": 0}):
        assert main(["+update", "--force"]) == 0
        refresh.assert_called_once()
        with pytest.raises(SystemExit) as exc:
            main(["--force", "update"])
    assert exc.value.code == 2
    assert refresh.call_count == 1
    assert "unrecognized arguments" in capsys.readouterr().err


def test_main_search_sort_by_name(capsys):
    pkgs = [_pkg("zzz", installs_30d=99_999), _pkg("aaa", installs_30d=1)]
    with patch("brewq.cache.load", return_value=_loaded(pkgs)):
        rc = main(["aaa", "-s", "name"])
    assert rc == 0


def test_main_search_sort_invalid(capsys):
    pkgs = [_pkg("ripgrep")]
    with patch("brewq.cache.load", return_value=_loaded(pkgs)):
        rc = main(["ripgrep", "-s", "bogus"])
    assert rc == 1
    assert "Unknown sort field" in capsys.readouterr().err


@pytest.mark.parametrize("flag", ["-i", "--installed"])
def test_main_search_installed_filter(capsys, flag):
    pkgs = [
        _pkg("installed-tool", installed=True, installs_30d=1_000),
        _pkg("other-tool", installed=False, installs_30d=5_000),
    ]
    with patch("brewq.cache.load", return_value=_loaded(pkgs)):
        rc = main([flag, "tool"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "installed-tool" in out
    assert "other-tool" not in out


@pytest.mark.parametrize("sort,expected", [
    ([], ["z-formula", "b-cask", "a-formula"]),
    (["-s", "name"], ["a-formula", "b-cask", "z-formula"]),
])
def test_installed_view_metric_and_alphabetical_sort_across_types(capsys, sort, expected):
    packages = [_pkg("a-formula", installed=True),
                _pkg("b-cask", type_="cask", installed=True),
                _pkg("z-formula", installed=True), _pkg("uninstalled")]
    for i, pkg in enumerate(packages):
        pkg.installs_90d = i * 100
    with patch("brewq.cache.load", return_value=_loaded(packages)):
        assert main(["-i", *sort, "--tsv", "-c", "name"]) == 0
    assert capsys.readouterr().out.splitlines() == expected


@pytest.mark.parametrize("args", [["-i", "-t", "2"], ["--installed", "-t", "2"]])
def test_installed_views_default_to_name_and_description(args, capsys):
    with patch("brewq.cache.load", return_value=_loaded([_pkg("ripgrep", installed=True)])):
        assert main(args) == 0
    output = capsys.readouterr().out
    assert "NAME" in output and "DESC" in output
    assert "TYPE" not in output and "VER" not in output
    assert "TREND" not in output and "90d" not in output


@pytest.mark.parametrize("command", [["-i"], ["--installed"]])
def test_installed_views_honor_list_config_and_explicit_columns(command, tmp_path, capsys):
    (tmp_path / "config.toml").write_text('installed-columns = ["name", "ver"]\n')
    with patch("brewq.cache.load", return_value=_loaded([_pkg("ripgrep", installed=True)])):
        assert main(command) == 0
        output = capsys.readouterr().out
        assert "VER" in output and "DESC" not in output
        assert main([*command, "-c", "name,type"]) == 0
        output = capsys.readouterr().out
        assert "TYPE" in output and "VER" not in output
        assert main([*command, "-c", "all"]) == 0
        output = capsys.readouterr().out
        assert "TYPE" in output and "VER" in output and "30d" in output
        assert "TREND" not in output  # This fixture has no historical counts.


@pytest.mark.parametrize("argv", [["-t", "2", "tool"], ["-i", "-t", "2"]])
def test_view_cap_discloses_shown_and_eligible_counts(argv, capsys):
    packages = [_pkg(f"git-tool-{i:02d}", installed=True) for i in range(5)]
    with patch("brewq.cache.load", return_value=_loaded(packages)):
        assert main(argv) == 0
    captured = capsys.readouterr()
    assert "showing 2 of 5; -a for all, -t N for a count" in captured.err
    assert "showing" not in captured.out


def test_no_view_cap_prints_no_notice(capsys):
    packages = [_pkg(f"git-tool-{i:02d}", installed=True) for i in range(5)]
    with patch("brewq.cache.load", return_value=_loaded(packages)):
        assert main(["-i", "-c", "name", "--tsv", "tool"]) == 0
    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 5
    assert "showing" not in captured.err


@pytest.mark.parametrize("count", [0, 1, 2])
def test_cap_is_silent_when_every_match_fits(count, capsys):
    packages = [_pkg(f"tool-{i}") for i in range(count)]
    with patch("brewq.cache.load", return_value=_loaded(packages)):
        assert main(["tool", "-t", "2", "--tsv", "-c", "name"]) == 0
    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == count
    assert "showing" not in captured.err
    assert "showing" not in captured.out


def test_main_search_discloses_stale_cache(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000)]
    with patch("brewq.cache.load", return_value=_loaded(pkgs, age=90_000)), \
         patch("brewq.scheduler.schedule_if_needed", return_value="scheduled"):
        rc = main(["ripgrep"])
    assert rc == 0
    assert "cache: 25h old; update scheduled" in capsys.readouterr().err


def test_main_list_short_field_names(capsys):
    with patch("brewq.cache.load", return_value=_loaded([
        _pkg("ripgrep", installed=True),
    ])):
        rc = main(["-i", "-c", "name,ver"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ripgrep" in out
    assert "DESC" not in out


def test_main_list_default_expansion_adds_url(capsys):
    with patch("brewq.cache.load", return_value=_loaded([
        _pkg("ripgrep", installed=True),
    ])):
        rc = main(["-i", "-c", "default,url"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "URL" in out
    assert "example.com" in out and "https://" not in out


def test_main_list_exact_metric_order(capsys):
    with patch("brewq.cache.load", return_value=_loaded([
        _pkg("ripgrep", installed=True, installs_30d=80_000, installs_90d=240_000),
    ])):
        rc = main(["-i", "-c", "name,90d,desc"])
    assert rc == 0
    header = next(line for line in capsys.readouterr().out.splitlines() if "NAME" in line)
    assert header.index("90d") < header.index("DESC")


def test_main_list_columns_show_multiple_metrics(capsys):
    with patch("brewq.cache.load", return_value=_loaded([
        _pkg("ripgrep", installed=True, installs_30d=80_000,
             installs_90d=240_000, installs_365d=600_000),
    ])):
        rc = main(["-i", "-c", "name,365d,90d,desc"])
    assert rc == 0
    header = next(line for line in capsys.readouterr().out.splitlines() if "NAME" in line)
    assert "365d" in header
    assert "90d" in header
    assert "30d" not in header


def test_main_list_uses_cache_without_brew(capsys):
    pkgs = [
        _pkg("ripgrep", installed=True, installs_30d=80_000),
        _pkg("bat", installed=False, installs_30d=50_000),
    ]
    with patch("brewq.cache.load", return_value=_loaded(pkgs, age=120)), \
         patch("subprocess.run", side_effect=AssertionError("called Homebrew")):
        rc = main(["-i"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "ripgrep" in captured.out
    assert "bat" not in captured.out
    assert "cache: 2min old" in captured.err


def test_installed_view_uses_configured_cap_and_explicit_override(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    (tmp_path / "config.toml").write_text('top = 2\n')
    packages = [
        _pkg(f"installed-{i:02d}", installed=True)
        for i in range(20)
    ]
    with patch("brewq.cache.load", return_value=_loaded(packages)):
        rc = main(["-i", "-c", "name"])
        captured = capsys.readouterr()
        assert "installed-01" in captured.out and "installed-02" not in captured.out
        assert "showing 2 of 20" in captured.err
        assert main(["-i", "-t", "20", "-c", "name"]) == 0
    assert rc == 0
    assert "installed-19" in capsys.readouterr().out


def test_cache_age_disclosure_uses_metadata_only(capsys):
    with patch("brewq.cache.status", side_effect=AssertionError("parsed full cache")), \
         patch("brewq.cache.load", return_value=_loaded([_pkg("ripgrep")], age=90)):
        rc = main(["ripgrep"])
    assert rc == 0
    assert "cache: 1min old" in capsys.readouterr().err


def test_search_terms_after_noncommand_are_not_rerouted(capsys):
    pkgs = [_pkg("cachelib", installs_30d=80_000)]
    with patch("brewq.cache.load", return_value=_loaded(pkgs)):
        rc = main(["cachelib", "cache"])
    assert rc == 0
    assert "cachelib" in capsys.readouterr().out


def test_main_search_without_match_reports_no_results(capsys):
    pkgs = [_pkg("tmux", installs_30d=80_000)]
    with patch("brewq.cache.load", return_value=_loaded(pkgs)):
        rc = main(["does-not-match"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "No results" in captured.err


def test_main_search_does_not_fetch_tapped_cache_misses(capsys):
    cached = [_pkg("font-sunshiney", type_="cask", installs_30d=60)]
    with patch("brewq.cache.load", return_value=_loaded(cached)), \
         patch("subprocess.run", side_effect=AssertionError("called Homebrew")):
        rc = main(["sunshine"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "font-sunshiney" in out
    assert "lizardbyte/homebrew/sunshine" not in out
    assert "unshield" not in out


def test_main_search_tsv(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000)]
    with patch("brewq.cache.load", return_value=_loaded(pkgs)):
        rc = main(["ripgrep", "--tsv", "-c", "name,30d,inst"])
    assert rc == 0
    assert capsys.readouterr().out == "ripgrep\t80000\tfalse\n"


def test_main_tsv_url_edit_adds_url_field(capsys):
    with patch("brewq.cache.load", return_value=_loaded([_pkg("ripgrep")])):
        rc = main(["--tsv", "-c", "name,url", "ripgrep"])
    assert rc == 0
    assert capsys.readouterr().out == "ripgrep\thttps://example.com\n"


def test_stale_cache_warning_respects_no_color(monkeypatch):
    stderr = io.StringIO()
    stderr.isatty = lambda: True
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr("brewq.cli.sys.stderr", stderr)
    with patch("brewq.cache.load", return_value=_loaded([_pkg("ripgrep")], age=90_000)), \
         patch("brewq.scheduler.schedule_if_needed", return_value="scheduled"):
        rc = main(["ripgrep"])
    assert rc == 0
    assert "25h old; update scheduled" in stderr.getvalue()
    assert "\033[" not in stderr.getvalue()


@pytest.mark.parametrize(
    ("source", "age", "complete", "message"),
    [("user", 90, True, "cache: 1min old"),
     ("user", 90_000, True, "cache: 25h old; update scheduled"),
     ("user", 90, False, "cache: metadata 1min old; analytics incomplete; update scheduled"),
     ("seed", 0, True, "cache: bundled seed; update scheduled")],
)
def test_cache_footer_is_neutral_and_subdued(monkeypatch, source, age, complete, message):
    stderr = io.StringIO()
    stderr.isatty = lambda: True
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setattr("brewq.cli.sys.stderr", stderr)
    with patch("brewq.cache.load", return_value=_loaded(
        [_pkg("ripgrep")], source=source, age=age, analytics_complete=complete,
    )), patch("brewq.scheduler.schedule_if_needed", return_value="scheduled"):
        assert main(["ripgrep"]) == 0
    assert stderr.getvalue() == f"\033[2m{message}\033[0m\n"


def test_random_script_runs_generated_search(capsys):
    script = Path(__file__).resolve().parents[1] / "scripts/random-layout.py"
    random_main = runpy.run_path(str(script))["main"]
    with patch("brewq.cli._cmd_search", return_value=0) as search:
        rc = random_main(["--seed", "7"])
    assert rc == 0
    generated = capsys.readouterr().err.strip()
    assert generated.startswith("brewq -t ")
    args = search.call_args.args[0]
    assert args.query
    assert args.sort in {"trend", "30d", "90d", "365d", "name"}
    assert not args.tsv


def test_main_search_bad_column(capsys):
    pkgs = [_pkg("ripgrep")]
    with patch("brewq.cache.load", return_value=_loaded(pkgs)):
        rc = main(["ripgrep", "--columns", "bogus"])
    assert rc == 1
    assert "Unknown column" in capsys.readouterr().err


def test_main_refresh_command(capsys):
    with patch("brewq.cache.refresh") as mock_refresh, \
         patch("brewq.cache.status", return_value={
             "formula_count": 1, "cask_count": 0
         }):
        rc = main(["+update"])
    assert rc == 0
    mock_refresh.assert_called_once()


@pytest.mark.parametrize("flag", ["-u", "--update"])
@pytest.mark.parametrize("command", [["ripgrep"], ["-i", "ripgrep"]])
def test_update_flag_refreshes_before_loading_and_querying(capsys, flag, command):
    pkgs = [_pkg("ripgrep", installs_30d=80_000)]
    pkgs[0].installed = True
    events = []

    def refresh_snapshot(*, force):
        assert force is True
        events.append("refresh")
        return RefreshResult(RefreshOutcome.COMPLETE, Path("/cache/brew-all.json"))

    def load_snapshot():
        events.append("load")
        return _loaded(pkgs)

    with patch("brewq.cache.refresh", side_effect=refresh_snapshot), \
         patch("brewq.cache.load", side_effect=load_snapshot):
        assert main([flag, *command]) == 0
    assert events == ["refresh", "load"]
    assert "ripgrep" in capsys.readouterr().out


@pytest.mark.parametrize("flag", ["-u", "--update"])
@pytest.mark.parametrize("outcome,message", [
    (RefreshOutcome.LOCKED, "already in progress"),
    (RefreshOutcome.METADATA_ONLY, "analytics incomplete"),
])
def test_update_query_continues_after_partial_or_locked_refresh(capsys, flag, outcome, message):
    with patch("brewq.cache.refresh", return_value=RefreshResult(
             outcome, Path("/cache/brew-all.json"), analytics_error="offline",
         )), patch("brewq.cache.load", return_value=_loaded([_pkg("ripgrep")])):
        assert main([flag, "ripgrep"]) == 0
    captured = capsys.readouterr()
    assert "ripgrep" in captured.out
    assert message in captured.err


def test_update_failure_without_usable_cache_reports_query_failure(capsys):
    with patch("brewq.cache.refresh", side_effect=OSError("offline")), \
         patch("brewq.cli._load_cache", return_value=None):
        assert main(["-u", "ripgrep"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "register update failed: offline" in captured.err


def test_main_config_path(capsys):
    rc = main(["+config", "path"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out.endswith("config.toml")


def test_seed_search_renders_before_scheduling(capsys):
    events = []
    loaded = _loaded([_pkg("ripgrep")], source="seed", age=100)
    with patch("brewq.cache.load", return_value=loaded), \
         patch("brewq.render.render_table", side_effect=lambda *args, **kwargs:
               events.append("render") or TableResult([], len(args[0]))), \
         patch(
             "brewq.scheduler.schedule_if_needed",
             side_effect=lambda *args, **kwargs: events.append("schedule") or "scheduled",
         ):
        rc = main(["ripgrep"])

    assert rc == 0
    assert events == ["render", "schedule"]
    assert "cache: bundled seed; update scheduled" in capsys.readouterr().err


def test_background_update_opt_out_renders_without_scheduler_state(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BREWQ_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("BREWQ_NO_AUTO_REFRESH", "1")
    loaded = _loaded([_pkg("ripgrep")], age=90_000)
    with patch("brewq.cache.load", return_value=loaded), \
         patch("brewq.scheduler.subprocess.Popen") as spawn:
        assert main(["ripgrep"]) == 0
    spawn.assert_not_called()
    assert list(tmp_path.iterdir()) == []
    captured = capsys.readouterr()
    assert "ripgrep" in captured.out
    assert "25h old" in captured.err
    assert "update scheduled" not in captured.err


def test_explicit_update_still_runs_when_background_updates_are_disabled(monkeypatch):
    monkeypatch.setenv("BREWQ_NO_AUTO_REFRESH", "1")
    with patch("brewq.cache.refresh", return_value=RefreshResult(
             RefreshOutcome.FRESH, Path("/cache/brew-all.json")
         )) as refresh:
        assert main(["+update"]) == 0
    refresh.assert_called_once_with(force=False)


def test_scheduler_failure_does_not_suppress_search_output(capsys):
    loaded = _loaded([_pkg("ripgrep")], source="seed", age=100)
    with patch("brewq.cache.load", return_value=loaded), \
         patch("brewq.scheduler.schedule_if_needed", side_effect=OSError("unavailable")):
        rc = main(["ripgrep"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "ripgrep" in captured.out
    assert "update not scheduled (unavailable)" in captured.err


def test_scheduler_cooldown_is_reported_truthfully(capsys):
    loaded = _loaded([_pkg("ripgrep")], source="seed", age=100)
    with patch("brewq.cache.load", return_value=loaded), \
         patch("brewq.scheduler.schedule_if_needed", return_value="cooldown"):
        assert main(["ripgrep"]) == 0
    assert "update deferred (cooldown)" in capsys.readouterr().err


def test_partial_cache_reports_metadata_age_and_incomplete_analytics(capsys):
    loaded = _loaded(
        [_pkg("ripgrep")],
        age=5,
        analytics_complete=False,
        repair_needed=True,
    )
    with patch("brewq.cache.load", return_value=loaded), \
         patch("brewq.scheduler.schedule_if_needed", return_value="cooldown"):
        assert main(["ripgrep"]) == 0

    assert (
        "cache: metadata 5s old; analytics incomplete; update deferred (cooldown)"
        in capsys.readouterr().err
    )


def test_stale_user_cache_renders_and_schedules(capsys):
    loaded = _loaded([_pkg("ripgrep")], age=90_000)
    with patch("brewq.cache.load", return_value=loaded), \
         patch("brewq.scheduler.schedule_if_needed", return_value="scheduled") as schedule:
        rc = main(["ripgrep"])

    assert rc == 0
    schedule.assert_called_once()
    assert "cache: 25h old; update scheduled" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("outcome", "error", "expected_rc", "message"),
    [
        (RefreshOutcome.FRESH, None, 0, "already fresh"),
        (RefreshOutcome.LOCKED, None, 1, "already in progress"),
        (RefreshOutcome.COMPLETE, None, 0, "register: updated"),
        (RefreshOutcome.METADATA_ONLY, "formula_30d: offline", 1, "analytics incomplete"),
    ],
)
def test_manual_refresh_reports_truthful_outcome(capsys, outcome, error, expected_rc, message):
    result = RefreshResult(outcome, Path("/cache/brew-all.json"), analytics_error=error)
    with patch("brewq.cache.refresh", return_value=result), \
         patch("brewq.cache.status", return_value={"formula_count": 1, "cask_count": 2}):
        rc = main(["+update"])

    assert rc == expected_rc
    assert message in capsys.readouterr().err


def test_main_list_missing_cache_is_empty_and_quick(capsys):
    with patch("brewq.cache.load", return_value=_loaded([], source="seed")), \
         patch("brewq.scheduler.schedule_if_needed", return_value="scheduled"), \
         patch("subprocess.run", side_effect=AssertionError("called Homebrew")):
        rc = main(["-i"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "brew not found" not in captured.err
    assert "cache: bundled seed; update scheduled" in captured.err


@pytest.mark.parametrize("command", [["ripgrep"], ["-i"]])
@pytest.mark.parametrize("field", ["inst", "status"])
def test_tsv_only_fields_rejected_before_cache(command, field, capsys):
    with patch("brewq.cache.load", side_effect=AssertionError("loaded cache")):
        assert main([*command, "-c", field]) == 1
    assert f"Column {field!r} is TSV-only; use --tsv" in capsys.readouterr().err


@pytest.mark.parametrize("command", [["ripgrep"], ["-i"]])
def test_all_tsv_includes_installed_state_and_status(command, capsys):
    pkg = _pkg("ripgrep", installed=True)
    pkg.disabled = True
    with patch("brewq.cache.load", return_value=_loaded([pkg])):
        assert main([*command, "-c", "all", "--tsv"]) == 0
    from brewq.columns import FULL_COLUMNS

    cells = capsys.readouterr().out.rstrip("\n").split("\t")
    assert len(cells) == len(FULL_COLUMNS)
    assert cells[FULL_COLUMNS.index("inst")] == "true"
    assert cells[FULL_COLUMNS.index("status")] == "disabled"


@pytest.mark.parametrize("command", [[], ["-i"]])
def test_help_has_inline_field_vocabulary(command, capsys):
    with pytest.raises(SystemExit) as exc:
        main([*command, "--help"])
    assert exc.value.code == 0
    help_text = capsys.readouterr().out
    assert ",".join(CANONICAL_COLUMNS) in help_text.replace("\n", "").replace(" ", "")


@pytest.mark.parametrize("argv,hidden,notes", [
    (["-c", "name,bin,desc", "json"], "bin", 1),
    (["-c", "all", "json"], "bin", 0),
    (["-c", "default", "font"], "desc", 0),
    (["-c", "default,bin", "json"], "bin", 1),
    (["-c", "default, bin", "font"], "desc", 0),
    (["-c", "name,desc", "font"], "desc", 1),
    (["font"], "desc", 0),
])
def test_table_omits_empty_columns_with_note_only_for_explicit_selection(capsys, argv, hidden, notes):
    pkg = _pkg("font-test" if "font" in argv else "json-tool")
    if "font" in argv:
        pkg.description = ""
    with patch("brewq.cache.load", return_value=_loaded([pkg])):
        assert main(argv) == 0
    captured = capsys.readouterr()
    header = next(line for line in captured.out.splitlines() if line.startswith("NAME"))
    assert hidden.upper() not in header.split()
    note = f"brewq: no {hidden} values in these results; column hidden"
    assert captured.err.count(note) == notes
    if argv[1:2] == ["default, bin"]:
        assert captured.err.count("column hidden") == 1
        assert "no bin values" in captured.err
    elif argv[1:2] in (["default"], ["all"]):
        assert "column hidden" not in captured.err


def test_installed_binary_column_remains_without_installed_marker(capsys):
    pkg = _pkg("json-tool", installed=True)
    pkg.binaries = ["json-tool"]
    with patch("brewq.cache.load", return_value=_loaded([pkg])):
        assert main(["-i", "-c", "name,bin"]) == 0
    captured = capsys.readouterr()
    assert "BIN" in captured.out and "json-tool  json-tool" in captured.out
    assert "✔" not in captured.out and "column hidden" not in captured.err


def test_tsv_keeps_empty_explicit_columns_without_notes(capsys):
    pkg = _pkg("json-tool")
    pkg.description = ""
    with patch("brewq.cache.load", return_value=_loaded([pkg])):
        assert main(["--tsv", "-c", "name,bin,desc", "json"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "json-tool\t\t\n"
    assert "column hidden" not in captured.err
