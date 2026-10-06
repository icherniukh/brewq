from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(tmp_path: Path, *args: str, env_override: dict[str, str] | None = None):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["BREWQ_CONFIG"] = str(tmp_path / "config.toml")
    env["BREWQ_CACHE_DIR"] = str(tmp_path / "cache")
    env.update(env_override or {})
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
    proc = _run(tmp_path, "--help", env_override={"BREWQ_CACHE_MAX_AGE": "invalid"})
    assert proc.returncode == 0
    assert "usage: brewq" in proc.stdout
    assert proc.stderr == ""


def test_compact_help_hides_legacy_and_advanced_shortcuts(tmp_path):
    proc = _run(tmp_path, "--help")
    assert proc.returncode == 0
    assert "-c, --columns" in proc.stdout
    assert "--full-help" in proc.stdout
    for hidden in ("-u, --url", "-v, --verbose", "--all", "-r, --refresh"):
        assert hidden not in proc.stdout

    list_proc = _run(tmp_path, "list", "--help")
    assert list_proc.returncode == 0
    for hidden in ("--analytics", "-u, --url", "-v, --verbose"):
        assert hidden not in list_proc.stdout


def test_full_help_ignores_invalid_operational_config(tmp_path):
    (tmp_path / "config.toml").write_text("search = 1\n")
    proc = _run(tmp_path, "--full-help", env_override={"BREWQ_CACHE_MAX_AGE": "invalid"})
    assert proc.returncode == 0
    assert "columns:" in proc.stdout
    assert "trending:" in proc.stdout
    assert "cache:" in proc.stdout
    assert proc.stderr == ""


def test_version_ignores_invalid_operational_config(tmp_path):
    proc = _run(tmp_path, "--version", env_override={"BREWQ_CACHE_MAX_AGE": "invalid"})
    assert proc.returncode == 0
    assert proc.stdout.startswith("brewq ")
    assert proc.stderr == ""


def test_config_path_ignores_invalid_operational_config(tmp_path):
    (tmp_path / "config.toml").write_text("output = []\n")
    proc = _run(tmp_path, "config", "path", env_override={"BREWQ_CACHE_MAX_AGE": "invalid"})
    assert proc.returncode == 0
    assert proc.stdout.strip() == str(tmp_path / "config.toml")
    assert proc.stderr == ""


def test_field_help_ignores_config_and_does_not_initialize_cache(tmp_path):
    (tmp_path / "config.toml").write_text("output = []\n")
    for args in [("-c", "help"), ("list", "-c", "help")]:
        proc = _run(tmp_path, *args, env_override={"BREWQ_CACHE_MAX_AGE": "invalid"})
        assert proc.returncode == 0
        assert "Output fields" in proc.stdout
        assert "installs_90d" in proc.stdout and "homepage" in proc.stdout
        assert "+version,bin" in proc.stdout and "-c all" in proc.stdout
        assert proc.stderr == ""
    assert not (tmp_path / "cache").exists()
