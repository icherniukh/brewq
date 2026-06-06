from __future__ import annotations

import io
import json

from brewq.columns import resolve
from brewq.model import Package
from brewq.render import render_json, render_table


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
    assert "INSTALLS" in text


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


def test_render_json_valid():
    out = io.StringIO()
    cols = resolve("name,type,installs", [])
    render_json([_pkg()], cols, out=out)
    records = json.loads(out.getvalue())
    assert len(records) == 1
    assert records[0]["name"] == "ripgrep"
    assert records[0]["type"] == "formula"


def test_render_json_installs_as_string():
    out = io.StringIO()
    cols = resolve("installs", [])
    render_json([_pkg(installs_30d=80_000)], cols, out=out)
    records = json.loads(out.getvalue())
    # JSON output is display string (formatted), not raw int
    assert records[0]["installs"] == "80,000"


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
