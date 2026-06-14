from __future__ import annotations

import io

from brewq.columns import resolve
from brewq.model import Package
from brewq.render import render_table, render_tsv


class TtyStringIO(io.StringIO):
    def isatty(self) -> bool:
        return True


def _pkg(name: str = "ripgrep", type_: str = "formula", installs_30d: int = 80_000,
         desc: str = "Search tool like grep and The Silver Searcher",
         installed: bool = False, status: str = "") -> Package:
    deprecated = status == "deprecated"
    disabled = status == "disabled"
    return Package(
        name=name, type=type_, description=desc, url="https://example.com",
        version="1.0", installs_30d=installs_30d, installs_365d=600_000,
        installed=installed, deprecated=deprecated, disabled=disabled,
    )


def test_render_table_contains_name():
    out = io.StringIO()
    pkgs = [_pkg()]
    cols = resolve("name,installs,description", [])
    render_table(pkgs, cols, out=out)
    assert "ripgrep" in out.getvalue()


def test_render_table_contains_header():
    out = io.StringIO()
    cols = resolve("name,type,installs", [])
    render_table([_pkg()], cols, out=out)
    text = out.getvalue()
    assert "NAME" in text
    assert "INSTALLS(30d)" in text


def test_render_table_installs_header_uses_selected_metric():
    out = io.StringIO()
    cols = resolve("installs", [])
    render_table([_pkg()], cols, metric="installs-365d", out=out)
    assert "INSTALLS(365d)" in out.getvalue()


def test_render_table_formats_installs_with_comma():
    out = io.StringIO()
    cols = resolve("installs", [])
    render_table([_pkg(installs_30d=528_018)], cols, out=out)
    assert "528,018" in out.getvalue()


def test_render_table_unknown_installs():
    out = io.StringIO()
    cols = resolve("installs", [])
    render_table([_pkg(installs_30d=-1)], cols, out=out)
    assert "-" in out.getvalue()


def test_render_tsv_uses_raw_values():
    out = io.StringIO()
    cols = resolve("name,type,installs", [])
    render_tsv([_pkg()], cols, out=out)
    assert out.getvalue() == "ripgrep\tformula\t80000\n"


def test_render_tsv_unknown_installs_are_blank():
    out = io.StringIO()
    cols = resolve("installs", [])
    render_tsv([_pkg(installs_30d=-1)], cols, out=out)
    assert out.getvalue() == "\n"


def test_render_tsv_installed_is_text_boolean():
    out = io.StringIO()
    cols = resolve("installed", [])
    render_tsv([_pkg(installed=True)], cols, out=out)
    assert out.getvalue() == "true\n"


def test_render_tsv_sanitizes_tabs_and_newlines():
    out = io.StringIO()
    cols = resolve("description", [])
    render_tsv([_pkg(desc="line one\tline two\nline three")], cols, out=out)
    assert out.getvalue() == "line one line two line three\n"


def test_render_table_multiple_packages():
    out = io.StringIO()
    pkgs = [_pkg("ripgrep"), _pkg("bat", installs_30d=50_000, desc="Cat clone")]
    cols = resolve("compact", [])
    render_table(pkgs, cols, out=out)
    text = out.getvalue()
    assert "ripgrep" in text
    assert "bat" in text


def test_render_table_no_color_when_no_color_env(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    out = io.StringIO()
    out.isatty = lambda: True  # simulate tty
    cols = resolve("name,installs", [])
    render_table([_pkg()], cols, out=out)
    # Should not contain ANSI escape codes
    assert "\033[" not in out.getvalue()


def test_render_table_colors_formulae_and_casks_differently(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    out = TtyStringIO()
    cols = resolve("name,installs", [])
    render_table([
        _pkg("ripgrep", type_="formula"),
        _pkg("google-chrome", type_="cask"),
    ], cols, out=out)
    text = out.getvalue()
    assert "\033[38;5;183mripgrep" in text
    assert "\033[38;5;115mgoogle-chrome" in text


def test_render_table_marks_deprecated_in_default_description():
    out = io.StringIO()
    cols = resolve("name,version,installs,description", [])
    render_table([_pkg(status="deprecated")], cols, out=out)
    assert "(deprecated) Search tool" in out.getvalue()


def test_render_table_marks_disabled_in_default_description():
    out = io.StringIO()
    cols = resolve("name,version,installs,description", [])
    render_table([_pkg(status="disabled")], cols, out=out)
    assert "(disabled) Search tool" in out.getvalue()


def test_render_table_status_prefix_wraps_inside_description_column(monkeypatch):
    monkeypatch.setattr("brewq.render._terminal_width", lambda: 80)
    out = io.StringIO()
    cols = resolve("name,version,installs,description", [])
    pkg = _pkg(
        name="zenmap",
        desc="Multi-platform graphical interface for official Nmap Security Scanner",
        status="deprecated",
    )
    render_table([pkg], cols, out=out)
    lines = [line for line in out.getvalue().splitlines() if line]
    assert all(len(line) <= 80 for line in lines)
    assert "(deprecated) Multi-platform" in out.getvalue()
    assert "Security Scanner" in out.getvalue()


def test_render_table_separator_stays_within_terminal_width(monkeypatch):
    monkeypatch.setattr("brewq.render._terminal_width", lambda: 80)
    out = io.StringIO()
    cols = resolve("name,version,installs,description", [])
    render_table([_pkg()], cols, out=out)
    separator = next(line for line in out.getvalue().splitlines() if line.startswith("─"))
    assert len(separator) <= 80
