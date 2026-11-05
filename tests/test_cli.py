from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import patch

import pytest

from brewq.cache import CacheLoad, RefreshOutcome, RefreshResult
from brewq.cli import main
from brewq.columns import CANONICAL_COLUMNS
from brewq.model import Package


def _pkg(name: str, type_: str = "formula", installs_30d: int = 10_000,
         installed: bool = False) -> Package:
    return Package(
        name=name, type=type_, description=f"Description of {name}",
        url="https://example.com", version="1.0",
        installs_30d=installs_30d, installs_90d=-1, installs_365d=-1,
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


def test_main_no_args_prints_help(capsys):
    rc = main([])
    assert rc == 2
    out = capsys.readouterr().out
    assert "commands:" in out
    assert "examples:" in out
    assert "-s" in out


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
    assert "-r, --refresh" in out


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


def test_main_search_tty_caps_by_terminal_height():
    import os

    import brewq.options as opts_mod

    pkgs = [
        _pkg(f"git-tool-{i:02d}", installs_30d=10_000 - i)
        for i in range(45)
    ]
    captured = []
    orig = opts_mod.build_search_options

    def spy(args, cfg, *, tty_rows=None):
        result = orig(args, cfg, tty_rows=tty_rows)
        captured.append(result)
        return result

    with patch("brewq.cache.load", return_value=_loaded(pkgs)), \
         patch("brewq.cli.sys.stdout") as mock_out, \
         patch("brewq.cli.shutil.get_terminal_size", return_value=os.terminal_size((120, 24))), \
         patch("brewq.options.build_search_options", side_effect=spy):
        mock_out.isatty.return_value = True
        main(["git"])

    assert captured, "build_search_options was not called"
    assert captured[0].limit == 18  # max(5, 24 - 6)


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


@pytest.mark.parametrize("command", [[], ["list"]])
@pytest.mark.parametrize("flag", ["-t", "--top", "--limit"])
@pytest.mark.parametrize("value", ["0", "-1", "nope", "1.5"])
def test_main_rejects_invalid_row_limits(command, flag, value):
    with pytest.raises(SystemExit) as exc:
        main([*command, flag, value])
    assert exc.value.code == 2


@pytest.mark.parametrize("command", [[], ["list"]])
@pytest.mark.parametrize("flag", ["-t", "--top", "--limit"])
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
    pkgs = [_pkg("ripgrep", installs_30d=80_000)]
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
        '[output]\ncolumns = ["name", "trending", "auto", "description"]\n'
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
    assert "TREND" in out
    assert "365d" in out
    assert "30d" not in out
    assert "90d" not in out


@pytest.mark.parametrize(
    ("argv", "expected"),
    [(["ripgrep", "-c", "+version,bin", "--tsv"], "ripgrep\t\t\t1.0\t\tDescription of ripgrep\n"),
     (["ripgrep", "-c", "+home,-trend", "--tsv"], "ripgrep\t\thttps://example.com\tDescription of ripgrep\n"),
     (["list", "-c", "+90d,trend", "--tsv"], "ripgrep\tformula\t1.0\t\t\tDescription of ripgrep\n")],
)
def test_column_edits_search_and_list_tsv(capsys, argv, expected):
    with patch("brewq.cache.load", return_value=_loaded([_pkg("ripgrep", installed=True)])):
        assert main(argv) == 0
    assert capsys.readouterr().out == expected


def test_edits_respect_custom_layout_and_resolve_auto_after_ranking(capsys, tmp_path):
    (tmp_path / "config.toml").write_text('[output]\ncolumns = ["auto"]\n')
    pkg = _pkg("ripgrep")
    pkg.installs_30d = -1
    pkg.installs_365d = 40_000
    with patch("brewq.cache.load", return_value=_loaded([pkg])):
        assert main(["ripgrep", "-c=-90d", "--tsv"]) == 0
    assert capsys.readouterr().out == "40000\n"


@pytest.mark.parametrize("spec", ["+bogus", "+auto", "+version,", "name,bogus"])
def test_invalid_selection_fails_before_loading_cache(capsys, spec):
    with patch("brewq.cache.load", side_effect=AssertionError("loaded cache")):
        assert main(["ripgrep", "-c", spec]) == 1
    assert "brewq:" in capsys.readouterr().err


def test_all_fields_matches_legacy_verbose(capsys):
    with patch("brewq.cache.load", return_value=_loaded([_pkg("ripgrep")])):
        assert main(["ripgrep", "-c", "all", "--tsv"]) == 0
        all_fields = capsys.readouterr().out
        assert main(["ripgrep", "-v", "--tsv"]) == 0
        assert capsys.readouterr().out == all_fields


def test_main_search_columns_short_alias(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000)]
    with patch("brewq.cache.load", return_value=_loaded(pkgs)):
        rc = main(["ripgrep", "-c", "name,installs"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ripgrep" in out
    assert "DESCRIPTION" not in out


def test_main_search_verbose_shows_all_fields(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000)]
    with patch("brewq.cache.load", return_value=_loaded(pkgs)):
        rc = main(["ripgrep", "-v"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ripgrep" in out
    for header in (
        "TYPE", "VERSION", "INST", "STATUS", "30d", "90d", "365d", "TREND",
        "BINARIES", "URL",
    ):
        assert header in out


def test_main_search_rejects_explicit_auto_column(capsys):
    with patch("brewq.cache.load", return_value=_loaded([_pkg("ripgrep")])):
        rc = main(["ripgrep", "-c", "auto"])
    assert rc == 1
    assert "only available in search configuration" in capsys.readouterr().err


def test_main_search_url_flag_adds_url_column(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000)]
    with patch("brewq.cache.load", return_value=_loaded(pkgs)):
        rc = main(["ripgrep", "-u"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "URL" in out
    assert "https://example.com" in out


def test_main_search_rejects_columns_with_verbose(capsys):
    pkgs = [_pkg("ripgrep")]
    with patch("brewq.cache.load", return_value=_loaded(pkgs)):
        rc = main(["ripgrep", "-c", "name", "-v"])
    assert rc == 1
    assert "cannot use both" in capsys.readouterr().err


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


def test_main_search_discloses_stale_cache(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000)]
    with patch("brewq.cache.load", return_value=_loaded(pkgs, age=90_000)), \
         patch("brewq.scheduler.schedule_if_needed", return_value="scheduled"):
        rc = main(["ripgrep"])
    assert rc == 0
    assert "cache: 25h old; refresh scheduled" in capsys.readouterr().err


def test_main_list_columns_short_alias(capsys):
    with patch("brewq.cache.load", return_value=_loaded([
        _pkg("ripgrep", installed=True),
    ])):
        rc = main(["list", "-c", "name,version"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ripgrep" in out
    assert "DESCRIPTION" not in out


def test_main_list_url_flag_adds_url_column(capsys):
    with patch("brewq.cache.load", return_value=_loaded([
        _pkg("ripgrep", installed=True),
    ])):
        rc = main(["list", "-u"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "URL" in out
    assert "https://example.com" in out


def test_main_list_analytics_inserts_installs_before_description(capsys):
    with patch("brewq.cache.load", return_value=_loaded([
        _pkg("ripgrep", installed=True, installs_30d=80_000),
    ])):
        rc = main(["list", "--analytics"])
    assert rc == 0
    header = next(line for line in capsys.readouterr().out.splitlines() if "NAME" in line)
    assert header.index("90d") < header.index("DESCRIPTION")


def test_main_list_analytics_adds_90d_alongside_other_metric(capsys):
    with patch("brewq.cache.load", return_value=_loaded([
        _pkg("ripgrep", installed=True, installs_30d=80_000),
    ])):
        rc = main(["list", "--analytics", "-c", "name,installs_365d,description"])
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
        rc = main(["list"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "ripgrep" in captured.out
    assert "bat" not in captured.out
    assert "cache: 2min old" in captured.err


def test_main_list_does_not_inherit_search_result_limit(capsys):
    packages = [
        _pkg(f"installed-{i:02d}", installed=True)
        for i in range(20)
    ]
    with patch("brewq.cache.load", return_value=_loaded(packages)):
        rc = main(["list", "-c", "name"])
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
        rc = main(["ripgrep", "--tsv", "-c", "name,installs,installed"])
    assert rc == 0
    assert capsys.readouterr().out == "ripgrep\t80000\tfalse\n"


def test_main_tsv_url_flag_adds_url_field(capsys):
    with patch("brewq.cache.load", return_value=_loaded([_pkg("ripgrep")])):
        rc = main(["-u", "--tsv", "-c", "name", "ripgrep"])
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
    assert "25h old; refresh scheduled" in stderr.getvalue()
    assert "\033[" not in stderr.getvalue()


@pytest.mark.parametrize(
    ("source", "age", "complete", "message"),
    [("user", 90, True, "cache: 1min old"),
     ("user", 90_000, True, "cache: 25h old; refresh scheduled"),
     ("user", 90, False, "cache: metadata 1min old; analytics incomplete; refresh scheduled"),
     ("seed", 0, True, "cache: bundled seed; refresh scheduled")],
)
def test_cache_footer_is_neutral_and_subdued(monkeypatch, source, age, complete, message):
    stderr = io.StringIO()
    stderr.isatty = lambda: True
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr("brewq.cli.sys.stderr", stderr)
    with patch("brewq.cache.load", return_value=_loaded(
        [_pkg("ripgrep")], source=source, age=age, analytics_complete=complete,
    )), patch("brewq.scheduler.schedule_if_needed", return_value="scheduled"):
        assert main(["ripgrep"]) == 0
    assert stderr.getvalue() == f"\033[2m{message}\033[0m\n"


def test_random_runs_generated_search(capsys):
    with patch("brewq.cli._cmd_search", return_value=0) as search:
        rc = main(["random", "--seed", "7"])
    assert rc == 0
    generated = capsys.readouterr().err.strip()
    assert generated.startswith("brewq -t ")
    args = search.call_args.args[0]
    assert args.query
    assert args.sort in {"trending", "30d", "90d", "365d", "name"}
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
        rc = main(["refresh"])
    assert rc == 0
    mock_refresh.assert_called_once()


def test_main_search_refresh_flag_refreshes_before_query(capsys):
    pkgs = [_pkg("ripgrep", installs_30d=80_000)]
    with patch("brewq.cache.refresh", return_value=RefreshResult(
             RefreshOutcome.COMPLETE, Path("/cache/brew-all.json")
         )) as refresh, \
         patch("brewq.cache.load", return_value=_loaded(pkgs)), \
         patch("brewq.cache.status", return_value={"formula_count": 1, "cask_count": 0}):
        rc = main(["-r", "ripgrep"])
    assert rc == 0
    refresh.assert_called_once_with(force=True)
    assert "ripgrep" in capsys.readouterr().out


def test_main_config_path(capsys):
    rc = main(["config", "path"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out.endswith("config.toml")


def test_seed_search_renders_before_scheduling(capsys):
    events = []
    loaded = _loaded([_pkg("ripgrep")], source="seed", age=100)
    with patch("brewq.cache.load", return_value=loaded), \
         patch("brewq.render.render_table", side_effect=lambda *args, **kwargs: events.append("render")), \
         patch(
             "brewq.scheduler.schedule_if_needed",
             side_effect=lambda *args, **kwargs: events.append("schedule") or "scheduled",
         ):
        rc = main(["ripgrep"])

    assert rc == 0
    assert events == ["render", "schedule"]
    assert "cache: bundled seed; refresh scheduled" in capsys.readouterr().err


def test_scheduler_failure_does_not_suppress_search_output(capsys):
    loaded = _loaded([_pkg("ripgrep")], source="seed", age=100)
    with patch("brewq.cache.load", return_value=loaded), \
         patch("brewq.scheduler.schedule_if_needed", side_effect=OSError("unavailable")):
        rc = main(["ripgrep"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "ripgrep" in captured.out
    assert "refresh not scheduled (unavailable)" in captured.err


def test_scheduler_cooldown_is_reported_truthfully(capsys):
    loaded = _loaded([_pkg("ripgrep")], source="seed", age=100)
    with patch("brewq.cache.load", return_value=loaded), \
         patch("brewq.scheduler.schedule_if_needed", return_value="cooldown"):
        assert main(["ripgrep"]) == 0
    assert "refresh deferred (cooldown)" in capsys.readouterr().err


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
        "cache: metadata 5s old; analytics incomplete; refresh deferred (cooldown)"
        in capsys.readouterr().err
    )


def test_stale_user_cache_renders_and_schedules(capsys):
    loaded = _loaded([_pkg("ripgrep")], age=90_000)
    with patch("brewq.cache.load", return_value=loaded), \
         patch("brewq.scheduler.schedule_if_needed", return_value="scheduled") as schedule:
        rc = main(["ripgrep"])

    assert rc == 0
    schedule.assert_called_once()
    assert "cache: 25h old; refresh scheduled" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("outcome", "error", "expected_rc", "message"),
    [
        (RefreshOutcome.FRESH, None, 0, "already fresh"),
        (RefreshOutcome.LOCKED, None, 1, "already in progress"),
        (RefreshOutcome.COMPLETE, None, 0, "cache: refreshed"),
        (RefreshOutcome.METADATA_ONLY, "formula_30d: offline", 1, "analytics incomplete"),
    ],
)
def test_manual_refresh_reports_truthful_outcome(capsys, outcome, error, expected_rc, message):
    result = RefreshResult(outcome, Path("/cache/brew-all.json"), analytics_error=error)
    with patch("brewq.cache.refresh", return_value=result), \
         patch("brewq.cache.status", return_value={"formula_count": 1, "cask_count": 2}):
        rc = main(["refresh"])

    assert rc == expected_rc
    assert message in capsys.readouterr().err


def test_main_list_missing_cache_is_empty_and_quick(capsys):
    with patch("brewq.cache.load", return_value=_loaded([], source="seed")), \
         patch("brewq.scheduler.schedule_if_needed", return_value="scheduled"), \
         patch("subprocess.run", side_effect=AssertionError("called Homebrew")):
        rc = main(["list"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "brew not found" not in captured.err
    assert "cache: bundled seed; refresh scheduled" in captured.err
