"""Real-terminal functional tests.

Unit tests in test_cli.py/test_render.py mock sys.stdout, isatty(), and
shutil.get_terminal_size() directly, so they never exercise the real OS-level
TTY detection or terminal-size wiring end to end. That gap let color/width/
row-cap regressions (installed-marker alignment, default output sizing) ship
with a fully green suite. These tests run the actual CLI under a real
pseudo-terminal instead.
"""

from __future__ import annotations

import fcntl
import json
import os
import pty
import re
import select
import shlex
import struct
import subprocess
import sys
import termios
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def _env(tmp_path: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    env["BREWQ_CACHE_DIR"] = str(tmp_path)
    env["BREWQ_CONFIG"] = str(tmp_path / "config.toml")
    # These rendering tests intentionally use cached installed metadata. Keep
    # local inventory unavailable so a developer machine's Homebrew state cannot
    # authoritatively replace the isolated fixture.
    env["PATH"] = str(tmp_path / "unavailable-bin")
    env.pop("NO_COLOR", None)
    env["TERM"] = "xterm-256color"
    env["BREWQ_NO_AUTO_REFRESH"] = "1"
    return env


def _formula(name: str, *, installed: bool = False, installs_30d: int = 1000,
             desc: str = "A tool for testing") -> dict:
    entry: dict = {
        "name": name, "full_name": name, "desc": desc, "homepage": "",
        "versions": {"stable": "1.0"}, "deprecated": False, "disabled": False,
        "aliases": [], "installs_30d": installs_30d, "installs_90d": -1, "installs_365d": -1,
    }
    if installed:
        entry["installed"] = [{"version": "1.0"}]
    return entry


def _write_cache(tmp_path: Path, formulae: list[dict], age_seconds: float = 5.0) -> None:
    path = tmp_path / "brew-all.json"
    path.write_text(json.dumps({
        "formulae": formulae,
        "casks": [],
        "_brewq_cache": {
            "schema_version": 1,
            "analytics_complete": True,
            "repair_needed": False,
        },
    }))
    mtime = time.time() - age_seconds
    os.utime(path, (mtime, mtime))


def _run_in_pty(
    argv: list[str], env: dict[str, str], *, rows: int = 30, cols: int = 120,
    timeout: float = 10.0, tty_stream: str = "both",
) -> tuple[int, str]:
    master_fd, slave_fd = pty.openpty()
    fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    proc = subprocess.Popen(
        argv, stdin=slave_fd,
        stdout=slave_fd if tty_stream in {"both", "stdout"} else subprocess.DEVNULL,
        stderr=slave_fd if tty_stream in {"both", "stderr"} else subprocess.DEVNULL,
        cwd=ROOT, env=env, close_fds=True, start_new_session=True,
    )
    os.close(slave_fd)
    chunks: list[bytes] = []
    deadline = time.monotonic() + timeout
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            ready, _, _ = select.select([master_fd], [], [], remaining)
            if not ready:
                break
            try:
                chunk = os.read(master_fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        try:
            os.close(master_fd)
        except OSError:
            pass
    try:
        returncode = proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        returncode = proc.wait()
    return returncode, b"".join(chunks).decode("utf-8", errors="replace")


def _brewq(*args: str) -> list[str]:
    return [sys.executable, "-m", "brewq.cli", *args]


def test_pty_table_is_colored_and_installed_marker_keeps_columns_aligned(tmp_path):
    _write_cache(tmp_path, [
        _formula("zzfunc-short", installs_30d=202_215),
        _formula("zzfunc-longer-name", installed=True, installs_30d=84_739),
    ])
    rc, output = _run_in_pty(_brewq("-t", "5", "-c", "name,30d", "zzfunc"), _env(tmp_path))
    assert rc == 0
    assert "\x1b[" in output, "real TTY output should carry color codes"

    lines = [_strip_ansi(line) for line in output.splitlines() if "zzfunc" in line]
    short_line = next(line for line in lines if "zzfunc-short" in line)
    long_line = next(line for line in lines if "zzfunc-longer-name" in line)
    assert "zzfunc-longer-name ✔" in long_line
    assert short_line.index("202,215") + len("202,215") == long_line.index("84,739") + len("84,739")


@pytest.mark.parametrize("rows,stale_lines", [(16, None), (26, None), (30, "10")])
@pytest.mark.parametrize("query", [[], [""], ["zzcap"]])
def test_pty_default_cap_keeps_typed_command_and_next_prompt_visible(tmp_path, rows, stale_lines, query):
    formulae = [_formula(f"zzcap-{i:02d}", installs_30d=10_000 - i) for i in range(40)]
    _write_cache(tmp_path, formulae)
    env = _env(tmp_path)
    if stale_lines:
        env["LINES"] = stale_lines
    command = shlex.join(["bq", *query])
    # Include the shell's typed line and next prompt in the visible viewport.
    shell = (f"printf '%s\\n' {shlex.quote('$ ' + command)}; "
             f"{shlex.join(_brewq(*query))}; result=$?; printf '%s' '$ '; exit $result")
    rc, output = _run_in_pty(["/bin/sh", "-c", shell], env, rows=rows, cols=120)
    assert rc == 0
    matched = [line for line in output.splitlines() if "zzcap-" in line]
    assert len(matched) == rows - 8
    assert f"showing {rows - 8} of 40" in output
    lines = _strip_ansi(output).splitlines()
    assert len(lines) == rows
    assert lines[-rows] == "$ " + command
    assert lines[-1] == "$ "


def test_pty_width_ignores_stale_columns(tmp_path):
    _write_cache(tmp_path, [_formula("zzwidth-long-package-name", desc="A long description " * 8)])
    env = _env(tmp_path)
    env["COLUMNS"] = "140"
    rc, output = _run_in_pty(_brewq("zzwidth"), env, cols=60)
    assert rc == 0
    assert all(len(line) <= 60 for line in _strip_ansi(output).splitlines())


@pytest.mark.parametrize("flags,expected", [
    ([], ["zzorder-high", "zzorder-mid"]),
    (["-a"], ["zzorder-low", "zzorder-mid", "zzorder-high"]),
    (["--all", "--no-reverse"], ["zzorder-high", "zzorder-mid", "zzorder-low"]),
    (["-a", "-t", "1"], ["zzorder-high"]),
    (["-t", "3"], ["zzorder-high", "zzorder-mid", "zzorder-low"]),
])
def test_pty_fixed_config_cap_all_and_explicit_override(tmp_path, flags, expected):
    formulae = []
    for name, count in [("high", 100), ("mid", 50), ("low", 1)]:
        entry = _formula(f"zzorder-{name}")
        entry["installs_90d"] = count
        formulae.append(entry)
    _write_cache(tmp_path, formulae)
    (tmp_path / "config.toml").write_text("top = 2\n")
    rc, output = _run_in_pty(_brewq(*flags, "-c", "name"), _env(tmp_path))
    assert rc == 0
    assert [line for line in _strip_ansi(output).splitlines() if line.startswith("zzorder-")] == expected


@pytest.mark.parametrize("query", [[], [""]])
def test_pty_empty_query_trend_browsing_and_installed_filter(tmp_path, query):
    popular = _formula("zzbrowse-popular", installed=True)
    popular.update(installs_90d=900_000, installs_365d=9_000_000)
    rising = _formula("zzbrowse-rising")
    rising.update(installs_90d=6000, installs_365d=6500)
    _write_cache(tmp_path, [popular, rising])
    for flags, expected, total in [
        ([], "zzbrowse-popular", 2),
        (["-s", "trend"], "zzbrowse-rising", 2),
        (["-i", "-s", "trend"], "zzbrowse-popular", 1),
    ]:
        rc, output = _run_in_pty(_brewq(*query, *flags, "-c", "name"), _env(tmp_path), rows=9)
        assert rc == 0
        records = [line for line in _strip_ansi(output).splitlines() if line.startswith("zzbrowse-")]
        assert len(records) == 1 and records[0].split()[0] == expected
        if total > 1:
            assert "showing 1 of 2" in output


@pytest.mark.parametrize("command", [[], ["-i"]])
@pytest.mark.parametrize("flag", ["-t", "--top"])
def test_pty_top_spellings_cap_both_commands(tmp_path, command, flag):
    _write_cache(tmp_path, [_formula(f"zzflags-{i}", installed=True) for i in range(8)])
    args = [*command, flag, "2"]
    if not command:
        args.extend(["-i", "zzflags"])
    rc, output = _run_in_pty(_brewq(*args), _env(tmp_path), rows=24, cols=100)
    assert rc == 0
    rows = [line for line in _strip_ansi(output).splitlines() if line.startswith("zzflags-")]
    assert len(rows) == 2
    assert "zzflags-0" in rows[0] and "zzflags-1" in rows[1]
    assert "zzflags-2" not in output


@pytest.mark.parametrize("command", [["-i"], ["--installed"]])
@pytest.mark.parametrize("width", [40, 60, 100])
def test_pty_installed_view_preserves_description_with_long_names(tmp_path, command, width):
    long_name = "a-very-long-vendor/tap/ghostty-ai-themes"
    _write_cache(tmp_path, [
        _formula(long_name, installed=True, desc="Useful description for this package"),
        _formula("short", installed=True, desc="Useful description for this package"),
    ])
    rc, output = _run_in_pty(_brewq(*command, "-t", "2"), _env(tmp_path), cols=width)
    assert rc == 0
    lines = _strip_ansi(output).splitlines()
    assert all(len(line) <= width for line in lines)
    header = next(line for line in lines if line.startswith("NAME"))
    assert "TYPE" not in header and "VER" not in header and "TREND" not in header
    rows = [line for line in lines if "Useful" in line]
    assert len(rows) == 2
    assert {line.index("Useful") for line in rows} == {header.index("DESC")}
    assert all("✔" in line for line in rows)
    assert any("…/" in line for line in rows)


def test_pty_non_tty_pipe_emits_no_ansi(tmp_path):
    _write_cache(tmp_path, [_formula("zzpipe-tool", installed=True)])
    proc = subprocess.run(
        _brewq("-t", "5", "zzpipe"), cwd=ROOT, env=_env(tmp_path),
        capture_output=True, text=True, timeout=10,
    )
    assert proc.returncode == 0
    assert "\x1b[" not in proc.stdout
    assert "\x1b[" not in proc.stderr


def test_pty_hot_trend_and_quiet_cache_footer(tmp_path):
    hot = _formula("zztrend-hot", installs_30d=80_000)
    hot.update(installs_90d=240_000, installs_365d=400_000)
    _write_cache(tmp_path, [hot])
    env = _env(tmp_path)
    rc, output = _run_in_pty(_brewq("zztrend"), env, cols=60)
    assert rc == 0
    assert re.search(r"\x1b\[1m\x1b\[32m *[0-9.]+x ↑↑\x1b\[0m", output)
    assert "\x1b[2mcache: " in output
    assert "\x1b[31m" not in output
    assert all(len(line) <= 60 for line in _strip_ansi(output).splitlines())

    env["NO_COLOR"] = "1"
    rc, output = _run_in_pty(_brewq("zztrend"), env, cols=60)
    assert rc == 0
    assert "↑↑" in output and "cache: " in output
    assert "\x1b[" not in output


@pytest.mark.parametrize("tty_stream", ["stdout", "stderr"])
@pytest.mark.parametrize("mode", ["normal", "empty-no-color", "no-color-env", "dumb", "flag"])
def test_pty_color_policy_for_each_stream(tmp_path, tty_stream, mode):
    hot = _formula("zzcolor-hot", installed=True)
    hot.update(installs_90d=240_000, installs_365d=400_000)
    _write_cache(tmp_path, [hot])
    env = _env(tmp_path)
    args = ["zzcolor"]
    if mode == "empty-no-color":
        env["NO_COLOR"] = ""
    elif mode == "no-color-env":
        env["NO_COLOR"] = "1"
    elif mode == "dumb":
        env["TERM"] = "dumb"
    elif mode == "flag":
        args.append("--no-color")
    rc, output = _run_in_pty(_brewq(*args), env, tty_stream=tty_stream)
    assert rc == 0
    assert ("\x1b[" in output) == (mode in {"normal", "empty-no-color"})
    if tty_stream == "stdout":
        assert "✔" in output and "↑↑" in output
        assert "cache:" not in output
    else:
        assert "cache:" in output and "zzcolor-hot" not in output


@pytest.mark.parametrize("mode", ["normal", "no-color-env", "dumb", "flag"])
@pytest.mark.parametrize("args", [["--bogus"], ["+update", "--bogus"], ["+list"], ["-v"]])
def test_pty_error_label_obeys_color_policy(tmp_path, mode, args):
    env = _env(tmp_path)
    if mode == "no-color-env":
        env["NO_COLOR"] = "1"
    elif mode == "dumb":
        env["TERM"] = "dumb"
    if mode == "flag":
        args = [*args, "--no-color"]
    rc, output = _run_in_pty(_brewq(*args), env, tty_stream="stderr")
    assert rc == 2
    assert "Error" in output
    assert ("\x1b[" in output) == (mode == "normal")


def test_pty_tsv_stdout_is_plain_even_on_color_terminal(tmp_path):
    _write_cache(tmp_path, [_formula("zztsv-tool", installed=True)])
    rc, output = _run_in_pty(
        _brewq("zztsv", "--tsv", "-c", "name,inst"), _env(tmp_path), tty_stream="stdout",
    )
    assert rc == 0
    assert output.splitlines() == ["zztsv-tool\ttrue"]
    assert "\x1b[" not in output
