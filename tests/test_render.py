from __future__ import annotations

import io
import os
import re
import unicodedata
from unittest.mock import PropertyMock, patch

import pytest

from brewq.columns import ColumnDef, resolve, select
from brewq.model import Package
from brewq.render import render_table, render_tsv


@pytest.mark.parametrize("tty", [False, True])
def test_terminal_size_uses_stdout_fd_before_environment(monkeypatch, tty):
    from brewq.render import terminal_size

    monkeypatch.setenv("LINES", "10")
    monkeypatch.setenv("COLUMNS", "140")
    with patch("brewq.render.sys.stdout") as stdout, \
         patch("os.get_terminal_size", return_value=os.terminal_size((60, 30))) as size:
        stdout.isatty.return_value = tty
        stdout.fileno.return_value = 42
        actual = terminal_size()
    assert actual == ((60, 30) if tty else (140, 10))
    if tty:
        size.assert_called_once_with(42)
    else:
        size.assert_not_called()


class TtyStringIO(io.StringIO):
    def isatty(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def color_terminal(monkeypatch):
    monkeypatch.setenv("TERM", "xterm-256color")


@pytest.mark.parametrize("tty", [False, True])
@pytest.mark.parametrize("term", ["xterm-256color", "dumb"])
@pytest.mark.parametrize("env_color", [None, "", "0", "1"])
@pytest.mark.parametrize("no_color", [False, True])
def test_shared_color_policy(monkeypatch, tty, term, env_color, no_color):
    from brewq.render import _use_color

    monkeypatch.setenv("TERM", term)
    if env_color is None:
        monkeypatch.delenv("NO_COLOR", raising=False)
    else:
        monkeypatch.setenv("NO_COLOR", env_color)
    out = TtyStringIO() if tty else io.StringIO()
    assert _use_color(out, no_color=no_color) == (
        tty and term != "dumb" and not env_color and not no_color
    )


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _pkg(name: str = "ripgrep", type_: str = "formula", installs_30d: int = 80_000,
         desc: str = "Search tool like grep and The Silver Searcher",
         installed: bool = False, status: str = "", version: str = "1.0") -> Package:
    deprecated = status == "deprecated"
    disabled = status == "disabled"
    return Package(
        name=name, type=type_, description=desc, url="https://example.com",
        version=version, installs_30d=installs_30d, installs_90d=240_000,
        installs_365d=600_000,
        installed=installed, deprecated=deprecated, disabled=disabled,
    )


def test_render_table_contains_header():
    out = io.StringIO()
    cols = resolve("name,type,30d", [])
    render_table([_pkg()], cols, out=out)
    text = out.getvalue()
    assert "NAME" in text
    assert "30d" in text


def test_render_table_metric_columns_use_lowercase_d_headers():
    out = io.StringIO()
    cols = resolve("30d,90d,365d", [])
    render_table([_pkg()], cols, out=out)
    text = out.getvalue()
    assert "30d" in text
    assert "90d" in text
    assert "365d" in text


def test_render_table_formats_installs_with_comma():
    out = io.StringIO()
    cols = resolve("30d", [])
    render_table([_pkg(installs_30d=528_018)], cols, out=out)
    assert "528,018" in out.getvalue()


def test_render_table_unknown_installs():
    out = io.StringIO()
    cols = resolve("30d", [])
    render_table([_pkg(installs_30d=-1)], cols, out=out)
    assert out.getvalue() == ""


def test_render_tsv_uses_raw_values():
    out = io.StringIO()
    cols = resolve("name,type,30d", [])
    render_tsv([_pkg()], cols, out=out)
    assert out.getvalue() == "ripgrep\tformula\t80000\n"


def test_render_tsv_unknown_installs_are_blank():
    out = io.StringIO()
    cols = resolve("30d", [])
    render_tsv([_pkg(installs_30d=-1)], cols, out=out)
    assert out.getvalue() == "\n"


def test_render_tsv_installed_is_text_boolean():
    out = io.StringIO()
    cols = resolve("inst", [])
    render_tsv([_pkg(installed=True)], cols, out=out)
    assert out.getvalue() == "true\n"


def test_render_tsv_sanitizes_tabs_and_newlines():
    out = io.StringIO()
    cols = resolve("desc", [])
    render_tsv([_pkg(desc="line one\tline two\nline three")], cols, out=out)
    assert out.getvalue() == "line one line two line three\n"


def test_render_table_no_color_when_no_color_env(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    out = io.StringIO()
    out.isatty = lambda: True  # simulate tty
    cols = resolve("name,30d", [])
    render_table([_pkg(installed=True)], cols, out=out)
    text = out.getvalue()
    assert "ripgrep ✔" in text
    assert "\033[" not in text


def test_render_table_non_tty_keeps_plain_installed_marker(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    out = io.StringIO()
    cols = resolve("name,30d", [])
    render_table([_pkg(installed=True)], cols, out=out)
    assert "ripgrep ✔" in out.getvalue()
    assert "\033[" not in out.getvalue()


def test_render_table_uses_theme_formula_cask_colors(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    out = TtyStringIO()
    cols = resolve("name", [])
    render_table(
        [_pkg("ripgrep"), _pkg("google-chrome", type_="cask")],
        cols,
        out=out,
    )
    text = out.getvalue()
    # Standard 16-color codes so package colors follow the terminal theme.
    assert "\033[36mripgrep" in text        # formula: cyan
    assert "\033[35mgoogle-chrome" in text  # cask: magenta


def test_render_table_theme_colors_still_respect_no_color(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    out = TtyStringIO()
    render_table([_pkg()], resolve("name", []), out=out)
    assert "\033[" not in out.getvalue()


def test_render_table_theme_colors_stay_plain_when_not_a_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    out = io.StringIO()
    render_table([_pkg()], resolve("name", []), out=out)
    assert "\033[" not in out.getvalue()


def test_render_table_marks_deprecated_in_default_description():
    out = io.StringIO()
    cols = resolve("name,ver,30d,desc", [])
    render_table([_pkg(status="deprecated")], cols, out=out)
    assert "(deprecated) Search tool" in out.getvalue()


def test_render_table_omits_description_status_prefix_when_status_column_selected():
    out = io.StringIO()
    cols = resolve("name,status,desc", [])
    render_table([_pkg(status="deprecated")], cols, out=out)
    text = out.getvalue()
    assert "deprecated" in text
    assert "(deprecated) Search tool" not in text
    assert "Search tool" in text


def test_render_table_status_prefix_stays_inside_description_column(monkeypatch):
    monkeypatch.setattr("brewq.render._terminal_width", lambda: 80)
    out = io.StringIO()
    cols = resolve("name,ver,30d,desc", [])
    pkg = _pkg(
        name="zenmap",
        desc="Multi-platform graphical interface for official Nmap Security Scanner",
        status="deprecated",
    )
    render_table([pkg], cols, out=out)
    lines = [line for line in out.getvalue().splitlines() if line]
    assert all(len(line) <= 80 for line in lines)
    assert "(deprecated) Multi-platform" in out.getvalue()


def test_render_table_status_prefix_clips_instead_of_wrapping(monkeypatch):
    monkeypatch.setattr("brewq.render._terminal_width", lambda: 72)
    out = io.StringIO()
    cols = resolve("name,ver,30d,desc", [])
    pkg = _pkg(
        name="libgit2@1.7",
        desc="C library of Git core methods that is re-entrant and linkable",
        status="disabled",
    )
    render_table([pkg], cols, out=out)
    lines = [line for line in out.getvalue().splitlines() if "libgit2@1.7" in line]
    assert len(lines) == 1
    assert "(disabled)" in lines[0]
    assert lines[0].endswith("…")


def test_render_table_separator_stays_within_terminal_width(monkeypatch):
    monkeypatch.setattr("brewq.render._terminal_width", lambda: 80)
    out = io.StringIO()
    cols = resolve("name,ver,30d,desc", [])
    render_table([_pkg()], cols, out=out)
    separator = next(line for line in out.getvalue().splitlines() if line.startswith("─"))
    assert len(separator) <= 80


def test_render_table_fits_sixty_column_terminal(monkeypatch):
    monkeypatch.setattr("brewq.render._terminal_width", lambda: 60)
    out = io.StringIO()
    cols = resolve("name,ver,30d,desc", [])
    pkg = _pkg(
        name="wezterm",
        version="20240203-110809,5046fc22",
        desc="GPU-accelerated cross-platform terminal emulator and multiplexer",
    )
    render_table([pkg], cols, out=out)
    lines = [line for line in out.getvalue().splitlines() if line]
    assert all(len(line) <= 60 for line in lines)


@pytest.mark.parametrize("width", [50, 80, 120, 200])
@pytest.mark.parametrize("spec", ["name,desc", "name,type,ver,desc"])
@pytest.mark.parametrize("no_color", [False, True])
def test_long_names_leave_description_space_and_fit(monkeypatch, width, spec, no_color):
    monkeypatch.setattr("brewq.render._terminal_width", lambda: width)
    if no_color:
        monkeypatch.setenv("NO_COLOR", "1")
    else:
        monkeypatch.delenv("NO_COLOR", raising=False)
    packages = [
        _pkg("a-very-long-vendor/tap/ghostty-ai-themes", installed=True,
             version="20261104-123456,abcdef012345", desc="Useful description for this package"),
        _pkg("short", desc="Useful description for this package"),
    ]
    out = TtyStringIO()
    render_table(packages, resolve(spec, []), out=out)
    lines = [_strip_ansi(line) for line in out.getvalue().splitlines() if line]
    assert all(len(line) <= width for line in lines)
    assert sum(line.count("✔") for line in lines) == 1
    if "NAME:" in out.getvalue():
        assert "DESC: Useful" in out.getvalue()
    else:
        header = lines[0]
        rows = [line for line in lines if "Useful" in line]
        assert len(rows) == 2
        assert {line.index("Useful") for line in rows} == {header.index("DESC")}
        name_width = len(packages[0].name) + 2
        fixed = 0 if spec == "name,desc" else 7 + 20 + 4
        if name_width + fixed + 2 + 20 <= width:
            assert packages[0].name + " ✔" in rows[0]
        elif spec == "name,desc":
            assert "…" in rows[0]
            assert header.index("DESC") == width - 20


def test_long_tap_names_keep_basename_and_tsv_identity(monkeypatch):
    monkeypatch.setattr("brewq.render._terminal_width", lambda: 50)
    name = "a-very-long-vendor/tap/ghostty-ai-themes"
    package = _pkg(name, installed=True)
    table, tsv = io.StringIO(), io.StringIO()
    columns = resolve("name,desc", [])
    render_table([package], columns, out=table)
    render_tsv([package], columns, out=tsv)
    assert "…/ghostty-ai-themes ✔" in table.getvalue()
    assert tsv.getvalue().startswith(name + "\t")


def test_too_narrow_tables_keep_selected_fields_in_vertical_records(monkeypatch):
    monkeypatch.setattr("brewq.render._terminal_width", lambda: 20)
    out = io.StringIO()
    render_table([_pkg("vendor/tap/very-long-name", installed=True, status="disabled")],
                 resolve("name,type,ver,desc", []), out=out)
    text = out.getvalue()
    assert all(len(line) <= 20 for line in text.splitlines())
    assert "NAME:" in text and "TYPE:" in text and "VER:" in text
    assert "DESC:" in text and "(disabled)" in text and "✔" in text


def test_render_table_installed_marker_keeps_columns_aligned(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    out = TtyStringIO()
    cols = resolve("name,30d,desc", [])
    render_table(
        [
            _pkg("awscli", installs_30d=202_215),
            _pkg("python@3.14", installed=True, installs_30d=84_739),
        ],
        cols,
        out=out,
    )

    lines = [_strip_ansi(line) for line in out.getvalue().splitlines()]
    awscli = next(line for line in lines if "awscli" in line)
    python = next(line for line in lines if "python@3.14" in line)
    assert "python@3.14 ✔" in python
    assert awscli.index("202,215") + len("202,215") == python.index("84,739") + len("84,739")
    assert awscli.index("Search tool") == python.index("Search tool")


@pytest.mark.parametrize(
    ("trend", "cue", "style"),
    [(None, "-", "\033[2m"), (0.74, "0.7x ↓", "\033[2m"),
     (0.79, "0.8x ·", "\033[2m"), (0.8, "0.8x ·", "\033[2m"),
     (1.19, "1.2x ↑", "\033[32m"), (1.2, "1.2x ↑", "\033[32m"),
     (1.99, "2.0x ↑↑", "\033[1m\033[32m"),
     (2.0, "2.0x ↑↑", "\033[1m\033[32m")],
)
def test_trend_bands_match_visible_precision_and_keep_tsv_raw(monkeypatch, trend, cue, style):
    monkeypatch.delenv("NO_COLOR", raising=False)
    cols = resolve("trend", [])
    table, tsv = TtyStringIO(), io.StringIO()
    with patch.object(Package, "trending", new_callable=PropertyMock, return_value=trend):
        render_table([_pkg()], cols, out=table)
        render_tsv([_pkg()], cols, out=tsv)
    if trend is None:
        assert table.getvalue() == ""
    else:
        assert cue in _strip_ansi(table.getvalue())
        assert style in table.getvalue()
    assert tsv.getvalue() == ("\n" if trend is None else f"{trend}\n")


@pytest.mark.parametrize("no_color", [False, True])
def test_trend_cues_keep_columns_aligned_and_fit_narrow_terminal(monkeypatch, no_color):
    if no_color:
        monkeypatch.setenv("NO_COLOR", "1")
    else:
        monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr("brewq.render._terminal_width", lambda: 60)
    out = TtyStringIO()
    packages = [_pkg("hot", installed=True), _pkg("rising"), _pkg("steady"), _pkg("cooling")]
    # Real model data exercises the whole presentation path, without mocked getters.
    for pkg, annual in zip(packages, [240_000, 400_000, 960_000, 2_000_000], strict=True):
        pkg.installs_365d = annual
    render_table(packages, resolve("name,trend,desc", []), out=out)
    lines = [_strip_ansi(line) for line in out.getvalue().splitlines() if line]
    assert all(len(line) <= 60 for line in lines)
    rows = [line for line in lines if "Search tool" in line]
    assert len({line.index("Search tool") for line in rows}) == 1
    assert len({line.index("x ") for line in rows}) == 1
    assert "↑↑" in rows[0] and "↑" in rows[1] and "·" in rows[2] and "↓" in rows[3]
    if no_color:
        assert "\033[" not in out.getvalue()


def test_piped_trend_keeps_cues_without_ansi():
    out = io.StringIO()
    pkg = _pkg()
    pkg.installs_365d = 240_000
    render_table([pkg], resolve("trend", []), out=out)
    assert "↑↑" in out.getvalue()
    assert "\033[" not in out.getvalue()


def _visible_width(text: str) -> int:
    return sum(0 if unicodedata.combining(c) else
               2 if unicodedata.east_asian_width(c) in {"W", "F"} else 1
               for c in _strip_ansi(text))


@pytest.mark.parametrize("width", [50, 80, 120, 200])
def test_names_keep_content_until_description_reaches_minimum(monkeypatch, width):
    monkeypatch.setattr("brewq.render._terminal_width", lambda: width)
    out = io.StringIO()
    name = "font-jetbrains-mono-nerd-font"
    render_table([_pkg(name, desc="Useful description " * 20)], resolve("name,desc", []), out=out)
    lines = [line for line in out.getvalue().splitlines() if line]
    assert all(_visible_width(line) <= width for line in lines)
    if len(name) + 2 + 20 <= width:
        assert lines[2].startswith(name + "  ")
    else:
        assert lines[0].index("DESC") == width - 20
        assert "…" in lines[2]


@pytest.mark.parametrize("width", [50, 70, 80, 120, 200])
@pytest.mark.parametrize("spec", ["name,desc,url", "all"])
@pytest.mark.parametrize("color", [False, True])
def test_display_width_bounds_cjk_and_combining_cells(monkeypatch, width, spec, color):
    monkeypatch.setattr("brewq.render._terminal_width", lambda: width)
    monkeypatch.delenv("NO_COLOR", raising=False)
    pkg = _pkg("sgn-工具-e\u0301", desc="跨平台文件搜索工具 e\u0301 " * 20, installed=True)
    pkg.url = "https://例子.com/工具"
    out = TtyStringIO() if color else io.StringIO()
    render_table([pkg], select(spec, []), out=out)
    assert all(_visible_width(line) <= width for line in out.getvalue().splitlines())
    assert "跨平台" in out.getvalue()


@pytest.mark.parametrize("scheme", ["https://", "http://"])
def test_only_https_scheme_is_removed_from_human_url(monkeypatch, scheme):
    monkeypatch.setattr("brewq.render._terminal_width", lambda: 200)
    pkg = _pkg()
    pkg.url = scheme + "example.com/path"
    table, tsv = io.StringIO(), io.StringIO()
    cols = resolve("name,url", [])
    render_table([pkg], cols, out=table)
    render_tsv([pkg], cols, out=tsv)
    assert (scheme in table.getvalue()) == (scheme == "http://")
    assert "example.com/path" in table.getvalue()
    assert tsv.getvalue() == f"ripgrep\t{pkg.url}\n"


@pytest.mark.parametrize("width", [20, 50, 80, 120, 200])
def test_installed_view_drops_marker_in_table_and_records(monkeypatch, width):
    monkeypatch.setattr("brewq.render._terminal_width", lambda: width)
    out = io.StringIO()
    render_table([_pkg(installed=True)], resolve("name,type,desc", []),
                 out=out, installed_only=True)
    assert "✔" not in out.getvalue()
    assert "ripgrep" in out.getvalue()


def test_records_skip_empty_fields_per_record_and_show_installed_once(monkeypatch):
    monkeypatch.setattr("brewq.render._terminal_width", lambda: 20)
    out = io.StringIO()
    packages = [_pkg("present", installed=True), _pkg("empty", desc="")]
    render_table(packages, resolve("name,type,inst,bin,url,desc", []), out=out)
    text = out.getvalue()
    assert text.count("✔") == 1
    assert "NAME: present ✔" not in text
    assert "INST: ✔" in text
    assert "BIN:" not in text
    empty_record = text.split("NAME: empty", 1)[1]
    assert "DESC:" not in empty_record and "INST:" not in empty_record
    assert "DESC:" in text


def test_empty_columns_reuse_getter_cells_and_tsv_retains_schema():
    calls = []
    cols = [ColumnDef("name", "NAME", "left", lambda p: calls.append(p.name) or ""),
            ColumnDef("bin", "BIN", "left", lambda p: calls.append("bin") or " - ")]
    out = io.StringIO()
    result = render_table([_pkg()], cols, out=out)
    assert calls == ["ripgrep", "bin"]
    assert result.hidden == ["bin"]
    assert "NAME" in out.getvalue() and "BIN" not in out.getvalue()
    tsv = io.StringIO()
    render_tsv([_pkg(desc="")], resolve("name,bin,desc", []), out=tsv)
    assert tsv.getvalue() == "ripgrep\t\t\n"


@pytest.mark.parametrize("width", [50, 80, 110, 120, 200])
def test_all_columns_preserve_short_metadata_using_records_when_needed(monkeypatch, width):
    monkeypatch.setattr("brewq.render._terminal_width", lambda: width)
    pkg = _pkg(version="57.12.3", desc="Useful description " * 4)
    pkg.binaries = ["a-long-executable-name"]
    pkg.url = "http://example.com/a/long/path"
    out = io.StringIO()
    render_table([pkg], select("all", []), out=out)
    text = out.getvalue()
    assert "formula" in text and "57.12.3" in text and "240,000" in text
    assert "for…" not in text and "57…" not in text and "ht…" not in text
    assert all(_visible_width(line) <= width for line in text.splitlines())
    assert ("NAME:" in text) == (width <= 120)


@pytest.mark.parametrize("width", [50, 80, 120, 200])
@pytest.mark.parametrize("status", ["disabled", "deprecated"])
@pytest.mark.parametrize("color", [False, True])
def test_full_status_description_is_budgeted_before_styling(monkeypatch, width, status, color):
    monkeypatch.setattr("brewq.render._terminal_width", lambda: width)
    monkeypatch.delenv("NO_COLOR", raising=False)
    out = TtyStringIO() if color else io.StringIO()
    packages = [_pkg("dotnet", status=status, desc=".NET Core"), _pkg("active", desc="Active")]
    render_table(packages, resolve("name,desc,url", []), out=out)
    text = _strip_ansi(out.getvalue())
    assert f"({status}) .NET Core" in text
    rows = [line for line in text.splitlines() if "example.com" in line]
    assert len(rows) == 2
    assert len({line.index("example.com") for line in rows}) == 1
    assert all(_visible_width(line) <= width for line in text.splitlines())
    assert ("\033[" in out.getvalue()) == color
    tsv = io.StringIO()
    render_tsv(packages, resolve("name,desc,status", []), out=tsv)
    assert tsv.getvalue().splitlines()[0] == f"dotnet\t.NET Core\t{status}"


@pytest.mark.parametrize("url,shown", [
    ("https://jsonnet.org/", "jsonnet.org"),
    ("http://jsonnet.org/", "http://jsonnet.org"),
    ("jsonnet.org/", "jsonnet.org"),
    ("/", "/"),
    ("https://github.com/mikefarah/yq", "github.com/mikefarah/yq"),
    ("https://example.com/a/", "example.com/a/"),
    ("https://example.com//", "example.com//"),
    ("https://example.com?next=/", "example.com?next=/"),
    ("https://example.com/#/", "example.com/#/"),
])
def test_table_url_trims_only_an_empty_root_path(monkeypatch, url, shown):
    monkeypatch.setattr("brewq.render._terminal_width", lambda: 200)
    pkg = _pkg()
    pkg.url = url
    table, tsv = io.StringIO(), io.StringIO()
    cols = resolve("url", [])
    render_table([pkg], cols, out=table)
    render_tsv([pkg], cols, out=tsv)
    assert table.getvalue().splitlines()[3] == shown
    assert tsv.getvalue() == url + "\n"


@pytest.mark.parametrize("reverse", [False, True])
def test_auto_vertical_budget_counts_wrapped_lines_and_keeps_best_records(monkeypatch, reverse):
    monkeypatch.setattr("brewq.render._terminal_width", lambda: 20)
    best = _pkg("best", desc="工具 " * 15)
    rest = _pkg("rest", desc="Short")
    packages = [rest, best] if reverse else [best, rest]
    out = io.StringIO()
    result = render_table(packages, resolve("name,type,desc", []), out=out,
                          auto_height=14, reverse=reverse)
    assert result.vertical and result.shown == 1
    assert "best" in out.getvalue() and "rest" not in out.getvalue()
    assert len(out.getvalue().splitlines()) + 4 <= 14


def test_auto_vertical_budget_always_keeps_one_record(monkeypatch):
    monkeypatch.setattr("brewq.render._terminal_width", lambda: 10)
    out = io.StringIO()
    result = render_table([_pkg(), _pkg("second")], resolve("name,type,desc", []),
                          out=out, auto_height=5)
    assert result.vertical and result.shown == 1
    assert "second" not in out.getvalue()
