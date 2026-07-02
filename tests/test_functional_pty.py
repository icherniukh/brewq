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
import struct
import subprocess
import sys
import termios
import time
from pathlib import Path

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
    env.pop("NO_COLOR", None)
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
    path.write_text(json.dumps({"formulae": formulae, "casks": []}))
    mtime = time.time() - age_seconds
    os.utime(path, (mtime, mtime))


def _run_in_pty(
    argv: list[str], env: dict[str, str], *, rows: int = 30, cols: int = 120,
    timeout: float = 10.0,
) -> tuple[int, str]:
    master_fd, slave_fd = pty.openpty()
    fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    proc = subprocess.Popen(
        argv, stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
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
    rc, output = _run_in_pty(_brewq("-t", "5", "-c", "name,installs", "zzfunc"), _env(tmp_path))
    assert rc == 0
    assert "\x1b[" in output, "real TTY output should carry color codes"

    lines = [_strip_ansi(line) for line in output.splitlines() if "zzfunc" in line]
    short_line = next(line for line in lines if "zzfunc-short" in line)
    long_line = next(line for line in lines if "zzfunc-longer-name" in line)
    assert "zzfunc-longer-name ✔" in long_line
    assert short_line.index("202,215") + len("202,215") == long_line.index("84,739") + len("84,739")


def test_pty_default_output_caps_by_real_terminal_height(tmp_path):
    formulae = [_formula(f"zzcap-{i:02d}", installs_30d=10_000 - i) for i in range(40)]
    _write_cache(tmp_path, formulae)
    rc, output = _run_in_pty(_brewq("zzcap"), _env(tmp_path), rows=20, cols=120)
    assert rc == 0
    matched = [line for line in output.splitlines() if "zzcap-" in line]
    # cli.py caps to max(5, rows - 6) when stdout is a real TTY; unit tests only
    # verify this by mocking sys.stdout and shutil.get_terminal_size wholesale.
    assert 0 < len(matched) <= 14
    assert "zzcap-39" not in output


def test_pty_non_tty_pipe_emits_no_ansi(tmp_path):
    _write_cache(tmp_path, [_formula("zzpipe-tool", installed=True)])
    proc = subprocess.run(
        _brewq("-t", "5", "zzpipe"), cwd=ROOT, env=_env(tmp_path),
        capture_output=True, text=True, timeout=10,
    )
    assert proc.returncode == 0
    assert "\x1b[" not in proc.stdout
    assert "\x1b[" not in proc.stderr
