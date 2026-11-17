from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from brewq import __version__

ROOT = Path(__file__).resolve().parents[1]


def _run(tmp_path: Path, *args: str):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["BREWQ_CONFIG"] = str(tmp_path / "config.toml")
    env["BREWQ_CACHE_DIR"] = str(tmp_path / "cache")
    return subprocess.run(
        [sys.executable, "-m", "brewq.cli", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_help_ignores_invalid_operational_config(tmp_path):
    (tmp_path / "config.toml").write_text("search = 1\n")
    proc = _run(tmp_path, "--help")
    assert proc.returncode == 0
    assert "usage: brewq" in proc.stdout
    assert proc.stderr == ""


def test_help_advertises_public_flags_only(tmp_path):
    proc = _run(tmp_path, "--help")
    assert proc.returncode == 0
    assert "-c, --columns" in proc.stdout
    assert "--full-help" in proc.stdout
    assert "-u, --update" in proc.stdout
    assert "-R, --reverse" in proc.stdout
    for hidden in ("--url", "--verbose", "--limit", "--refresh"):
        assert hidden not in proc.stdout

    assert "--all" in proc.stdout
    assert "--no-color" in proc.stdout
    assert "+list" not in proc.stdout
    removed = _run(tmp_path, "+list")
    assert removed.returncode == 2
    assert "unknown action +list" in removed.stderr


def test_full_help_ignores_invalid_operational_config(tmp_path):
    (tmp_path / "config.toml").write_text("search = 1\n")
    proc = _run(tmp_path, "--full-help")
    assert proc.returncode == 0
    assert "columns:" in proc.stdout
    assert "trending:" in proc.stdout
    assert "cache:" in proc.stdout
    assert proc.stderr == ""


@pytest.mark.parametrize("flag", ["-V", "--version"])
def test_version_ignores_invalid_operational_config(tmp_path, flag):
    (tmp_path / "config.toml").write_text("output = []\n")
    proc = _run(tmp_path, flag)
    assert proc.returncode == 0
    assert proc.stdout == f"brewq {__version__}\n"
    assert proc.stderr == ""


def test_config_path_ignores_invalid_operational_config(tmp_path):
    (tmp_path / "config.toml").write_text("output = []\n")
    proc = _run(tmp_path, "+config")
    assert proc.returncode == 0
    assert proc.stdout.strip() == str(tmp_path / "config.toml")
    assert proc.stderr == ""


def test_field_reference_ignores_config_and_does_not_initialize_cache(tmp_path):
    (tmp_path / "config.toml").write_text("output = []\n")
    for args in [("--full-help",), ("-i", "--full-help")]:
        proc = _run(tmp_path, *args)
        assert proc.returncode == 0
        assert "columns:" in proc.stdout
        assert "90d" in proc.stdout and "url" in proc.stdout
        assert "default,url" in proc.stdout and "-c all" in proc.stdout
        assert proc.stderr == ""
    assert not (tmp_path / "cache").exists()


@pytest.mark.parametrize("args,diagnostic", [
    (("+config", "path"), "unrecognized arguments: path"),
    (("--no-reverse",), "unrecognized arguments: --no-reverse"),
])
def test_unknown_arguments_are_usage_errors_without_cache_access(tmp_path, args, diagnostic):
    proc = _run(tmp_path, *args)
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert diagnostic in proc.stderr
    assert not (tmp_path / "cache").exists()


@pytest.mark.parametrize("args", [("-c", "help"), ("-i", "-c", "help")])
def test_help_is_an_unknown_column_without_cache_access(tmp_path, args):
    proc = _run(tmp_path, *args)
    assert proc.returncode == 1
    assert proc.stdout == ""
    assert "Unknown column 'help'." in proc.stderr
    assert "--full-help" in proc.stderr
    assert not (tmp_path / "cache").exists()


def test_unknown_installed_shorthand_is_rejected_before_cache_access(tmp_path):
    proc = _run(tmp_path, "-l", "tool")
    assert proc.returncode == 2
    assert "unrecognized arguments: -l" in proc.stderr
    assert not (tmp_path / "cache").exists()


def test_search_and_installed_help_share_top_spellings(tmp_path):
    for command in [(), ("-i",)]:
        proc = _run(tmp_path, *command, "--help")
        assert proc.returncode == 0
        assert "--top" in proc.stdout and "--limit" not in proc.stdout
        assert "-t" in proc.stdout
        if not command:
            assert "-i, --installed" in proc.stdout
            assert "-l, --installed" not in proc.stdout
    assert not (tmp_path / "cache").exists()


def test_broken_pipe_exits_quietly(tmp_path):
    import os
    import subprocess
    import sys

    env = {**os.environ, "BREWQ_CACHE_DIR": str(tmp_path), "BREWQ_CONFIG": str(tmp_path / "c.toml")}
    cmd = [sys.executable, "-m", "brewq.cli", "--tsv", "-c", "all", "a"]
    producer = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    assert producer.stdout is not None
    producer.stdout.readline()
    producer.stdout.close()
    stderr = producer.stderr.read().decode()
    producer.wait(timeout=60)
    assert "Traceback" not in stderr
