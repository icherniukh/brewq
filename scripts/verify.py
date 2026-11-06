#!/usr/bin/env python3
"""Single entrypoint for brewq's pre-PR verification suite.

Chains: ruff -> pytest -> functional CLI smoke checks -> installed shim check.
Replaces `bd preflight`, whose built-in checklist targets Go projects and does
not apply here (see brewq-1xx.1).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from brewq import __version__

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


@dataclass(frozen=True)
class Check:
    name: str
    run: object  # Callable[[], "Result"]


@dataclass(frozen=True)
class Result:
    name: str
    ok: bool
    detail: str = ""


def _env() -> dict[str, str]:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC) if not existing else f"{SRC}{os.pathsep}{existing}"
    return env


def _run(argv: Sequence[str], timeout: float = 30.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv, cwd=ROOT, env=_env(), capture_output=True, text=True, timeout=timeout
    )


def check_ruff() -> Result:
    proc = _run(["uv", "run", "ruff", "check", "."])
    return Result("ruff check", proc.returncode == 0, proc.stdout + proc.stderr)


def check_pytest() -> Result:
    proc = _run(["uv", "run", "pytest", "-q"], timeout=120.0)
    return Result("pytest", proc.returncode == 0, proc.stdout + proc.stderr)


def _brewq(*args: str) -> tuple[str, ...]:
    return (sys.executable, "-m", "brewq.cli", *args)


def check_cli_smoke() -> Result:
    cases: list[tuple[str, Sequence[str], Sequence[str]]] = [
        ("help", _brewq("--help"), ["usage"]),
        ("full_help", _brewq("--full-help"), ["columns:", "trending:", "cache:"]),
        ("search_table", _brewq("-t", "5", "json"), ["NAME"]),
        ("search_tsv", _brewq("--tsv", "-c", "name,30d", "ripgrep"), []),
        ("list_default", _brewq("list", "-t", "5"), ["NAME", "DESCRIPTION"]),
        ("list_metrics", _brewq("list", "-c", "name,90d", "--top", "5"), []),
        ("list_tsv", _brewq("list", "--tsv", "-c", "name,type", "--limit", "5"), []),
    ]
    failures = []
    for name, argv, must_contain in cases:
        proc = _run(argv, timeout=20.0)
        if proc.returncode != 0:
            failures.append(f"{name}: exit {proc.returncode}: {proc.stderr.strip()}")
            continue
        if "\x1b[" in proc.stdout:
            failures.append(f"{name}: ANSI escape codes leaked into non-TTY output")
            continue
        for needle in must_contain:
            if needle not in proc.stdout:
                failures.append(f"{name}: expected {needle!r} in output")
    ok = not failures
    return Result("cli smoke", ok, "\n".join(failures))


def _external_entrypoint(name: str) -> str | None:
    """Find a PATH entry outside the environment running this verification script."""
    active_bin = Path(sys.executable).absolute().parent
    for raw_dir in os.environ.get("PATH", "").split(os.pathsep):
        if not raw_dir:
            continue
        directory = Path(raw_dir).expanduser()
        try:
            if directory.resolve() == active_bin:
                continue
        except OSError:
            continue
        candidate = directory / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.absolute())
    return None


def check_installed_shim() -> Result:
    brewq_path = _external_entrypoint("brewq")
    if brewq_path is None:
        return Result(
            "installed shim",
            True,
            "skipped: brewq not on PATH outside the active environment",
        )

    failures = []
    expected_version = f"brewq {__version__}"
    for name in ("brewq", "bq"):
        path = _external_entrypoint(name)
        if path is None:
            missing = "shortcut missing; run brewq setup" if name == "bq" else "entry point missing from PATH"
            failures.append(f"{name}: {missing}")
            continue
        version = subprocess.run(
            [path, "--version"], capture_output=True, text=True, timeout=20.0
        )
        if version.returncode != 0 or version.stdout.strip() != expected_version:
            actual = (version.stdout + version.stderr).strip() or f"exit {version.returncode}"
            failures.append(f"{name}: expected {expected_version!r}, got {actual!r}")

    help_result = subprocess.run(
        [brewq_path, "--help"], capture_output=True, text=True, timeout=20.0
    )
    if help_result.returncode != 0:
        failures.append(f"brewq help: exit {help_result.returncode}: {help_result.stderr.strip()}")
    else:
        # argparse's metavar placement differs between supported Python versions.
        def advertised(flag: str) -> bool:
            return re.search(
                rf"(?<![\w-]){re.escape(flag)}(?=[\s,=]|$)", help_result.stdout,
            ) is not None

        for expected in (
            "-c", "--columns", "-i", "--installed", "-u", "--update", "-R", "--reverse",
            "--top", "--limit", "--full-help", "--tsv",
        ):
            if not advertised(expected):
                failures.append(f"brewq help: missing {expected!r}")
        for removed in ("-l", "--url", "-v", "--verbose", "--preset", "--colors"):
            if advertised(removed):
                failures.append(f"brewq help: stale option {removed!r} is still installed")

    # Exercise the actual entrypoints, not the checkout's module on PYTHONPATH.
    with tempfile.TemporaryDirectory(prefix="brewq-installed-check-") as directory:
        root = Path(directory)
        (root / "brew-all.json").write_text(json.dumps({
            "formulae": [
                {"name": name, "installed": [{"version": "1.0"}] if installed else [],
                 "installs_90d": count}
                for name, installed, count in [
                    ("zzverify-hidden", False, 100_000),
                    ("zzverify-installed-a", True, 1000),
                    ("zzverify-installed-b", True, 500),
                ]
            ],
            "casks": [],
            "_brewq_cache": {
                "schema_version": 1, "analytics_complete": True, "repair_needed": False,
            },
        }))
        env = {
            "HOME": directory, "PATH": str(root / "no-brew"),
            "BREWQ_CACHE_DIR": directory, "BREWQ_CONFIG": str(root / "config.toml"),
            "XDG_CACHE_HOME": directory, "XDG_CONFIG_HOME": directory,
            "NO_COLOR": "1", "TERM": "dumb", "PYTHONDONTWRITEBYTECODE": "1",
        }
        cases = [
            ["-i", "-t", "1", "--tsv", "-c", "name", "zzverify"],
            ["--installed", "--limit", "1", "--tsv", "-c", "name", "zzverify"],
            ["list", "--top", "1", "--tsv", "-c", "name"],
            ["list", "--limit", "1", "--tsv", "-c", "name"],
        ]
        for name in ("brewq", "bq"):
            path = _external_entrypoint(name)
            if path is None:
                continue  # Already reported above.
            for args in cases:
                proc = subprocess.run(
                    [path, *args], cwd=directory, env=env,
                    capture_output=True, text=True, timeout=20.0,
                )
                if proc.returncode != 0 or proc.stdout.splitlines() != ["zzverify-installed-a"]:
                    failures.append(f"{name} {' '.join(args)}: installed behavior mismatch")
            for args in (["-i", "-t", "1"], ["list", "-t", "1"]):
                proc = subprocess.run(
                    [path, *args], cwd=directory, env=env,
                    capture_output=True, text=True, timeout=20.0,
                )
                header = next((line for line in proc.stdout.splitlines() if line.startswith("NAME")), "")
                if (proc.returncode != 0 or "DESCRIPTION" not in header
                        or any(field in header for field in ("TYPE", "VERSION", "TREND", "90d"))):
                    failures.append(f"{name} {' '.join(args)}: installed default layout mismatch")
            completion = subprocess.run(
                [path, "completion", "zsh"], cwd=directory, env=env,
                capture_output=True, text=True, timeout=20.0,
            )
            if completion.returncode != 0 or "compdef _brewq brewq bq" not in completion.stdout:
                failures.append(f"{name}: installed completion generation failed")

    return Result("installed shim", not failures, "\n".join(failures))


CHECKS: tuple[Check, ...] = (
    Check("ruff check", check_ruff),
    Check("pytest", check_pytest),
    Check("cli smoke", check_cli_smoke),
    Check("installed shim", check_installed_shim),
)


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    failed = False
    for check in CHECKS:
        result: Result = check.run()
        status = "ok" if result.ok else "FAIL"
        print(f"[{status}] {result.name}")
        if not result.ok or result.detail.startswith("skipped:"):
            for line in result.detail.splitlines():
                print(f"    {line}")
        if not result.ok:
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
