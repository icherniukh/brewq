"""Subprocess tests against a preloaded cache. No Homebrew, network, or user state."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from brewq.cache import materialize

ROOT = Path(__file__).resolve().parents[1]


def _catalog() -> dict:
    def formula(name: str, installs_90d: int, *, installed: bool = False, desc: str = "") -> dict:
        record = {
            "name": name,
            "desc": desc or name,
            "homepage": f"https://example.test/{name}",
            "versions": {"stable": "1.0"},
            "installs_30d": installs_90d // 3,
            "installs_90d": installs_90d,
            "installs_365d": installs_90d * 4,
        }
        if installed:
            record["installed"] = [{"version": "1.0"}]
        return record

    return {
        "formulae": [
            formula("ripgrep", 900, desc="search tool"),
            formula("rg-tools", 10, desc="ripgrep helper"),
            formula("bat", 500, installed=True, desc="cat clone"),
            formula("list", 50, desc="not the inventory action"),
        ],
        "casks": [{
            "token": "font-test",
            "desc": "a font",
            "homepage": "https://example.test/font",
            "version": "1.0",
            "installs_30d": 1,
            "installs_90d": 4,
            "installs_365d": 9,
        }],
        "_brewq_cache": {
            "schema_version": 1,
            "analytics_complete": True,
            "repair_needed": False,
        },
    }


def _preload(tmp_path: Path) -> None:
    materialize(_catalog(), tmp_path / "cache")


def _run(tmp_path: Path, *args: str, env_override: dict[str, str] | None = None):
    env = {
        "PATH": str(tmp_path / "bin"),
        "HOME": str(tmp_path),
        "BREWQ_CACHE_DIR": str(tmp_path / "cache"),
        "BREWQ_CONFIG": str(tmp_path / "config.toml"),
        "BREWQ_NO_AUTO_REFRESH": "1",
        "NO_COLOR": "1",
        "TERM": "dumb",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(ROOT / "src"),
    }
    env.update(env_override or {})
    return subprocess.run(
        [sys.executable, "-m", "brewq.cli", *args],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_help_version_and_config_do_not_create_a_cache(tmp_path):
    assert _run(tmp_path, "--help").returncode == 0
    assert _run(tmp_path, "--version").stdout.startswith("brewq ")
    config = _run(tmp_path, "+config", "path")
    assert config.returncode == 0
    assert config.stdout.strip().endswith("config.toml")
    assert not (tmp_path / "cache" / "brew-all.json").exists()


def test_preloaded_search_list_cap_and_tsv(tmp_path):
    _preload(tmp_path)
    search = _run(tmp_path, "-c", "name", "--tsv", "ripgrep")
    assert search.returncode == 0
    assert search.stdout.splitlines() == ["ripgrep", "rg-tools"]
    assert "showing" not in search.stdout

    capped = _run(tmp_path, "-t", "1", "-c", "name", "--tsv", "ripgrep")
    assert capped.stdout.strip() == "ripgrep"
    assert "showing 1 of 2" in capped.stderr

    inventory = _run(tmp_path, "-i", "-c", "name", "--tsv")
    assert inventory.stdout.strip() == "bat"
    query = _run(tmp_path, "-c", "name", "--tsv", "list")
    assert query.stdout.strip() == "list"
    assert not (tmp_path / "cache" / "refresh-state.json").exists()


def test_flags_between_terms_and_unknown_action(tmp_path):
    _preload(tmp_path)
    found = _run(tmp_path, "rip", "-t", "1", "-c", "name", "--tsv", "grep")
    assert found.returncode == 0
    assert found.stdout.strip() == "ripgrep"

    bad = _run(tmp_path, "+nope")
    assert bad.returncode == 2
    assert bad.stdout == ""
    assert "Error: unknown action +nope" in bad.stderr
    assert "usage:" in bad.stderr


def test_update_offline_uses_the_bundled_catalog_without_homebrew(tmp_path):
    proc = _run(tmp_path, "+update", "--offline")
    assert proc.returncode == 0, proc.stderr
    assert "formulae" in proc.stdout
    cache = tmp_path / "cache" / "brew-all.json"
    assert cache.exists() and cache.stat().st_size > 1000
    follow = _run(tmp_path, "-t", "1", "-c", "name", "--tsv", "ripgrep")
    assert follow.returncode == 0, follow.stderr
    assert follow.stdout.strip() == "ripgrep"
    assert "bundled seed" not in follow.stderr


@pytest.mark.parametrize("flag", ["-u", "--update"])
@pytest.mark.parametrize("command", [["ripgrep"], ["-i", "bat"]])
def test_failed_update_queries_old_snapshot_without_changing_it(tmp_path, flag, command):
    _preload(tmp_path)
    snapshot = tmp_path / "cache" / "brew-all.json"
    before = snapshot.read_bytes(), snapshot.stat().st_mtime_ns
    proc = _run(tmp_path, flag, *command, "--tsv", "-c", "name,90d")
    assert proc.returncode == 0, proc.stderr
    expected = ["bat\t500"] if "-i" in command else ["ripgrep\t900", "rg-tools\t10"]
    assert proc.stdout.splitlines() == expected
    assert "register update failed" in proc.stderr
    assert "Updating register" not in proc.stdout
    assert (snapshot.read_bytes(), snapshot.stat().st_mtime_ns) == before


def test_failed_update_without_snapshot_uses_seed_offline(tmp_path):
    proc = _run(tmp_path, "-u", "ripgrep", "--tsv", "-c", "name", "-t", "1")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "ripgrep"
    assert "register update failed" in proc.stderr and "bundled seed" in proc.stderr
