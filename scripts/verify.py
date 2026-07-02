#!/usr/bin/env python3
"""Single entrypoint for brewq's pre-PR verification suite.

Chains: ruff -> pytest -> functional CLI smoke checks -> installed shim check.
Replaces `bd preflight`, whose built-in checklist targets Go projects and does
not apply here (see brewq-1xx.1).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

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
        ("search_table", _brewq("-t", "5", "json"), ["NAME"]),
        ("search_tsv", _brewq("--tsv", "-c", "name,30d", "ripgrep"), []),
        ("list_default", _brewq("list", "--limit", "5"), ["NAME", "TYPE"]),
        ("list_analytics", _brewq("list", "--analytics", "--limit", "5"), []),
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


def check_installed_shim() -> Result:
    brewq_path = shutil.which("brewq")
    if brewq_path is None:
        return Result("installed shim", True, "skipped: brewq not on PATH (no installed shim to check)")
    proc = subprocess.run([brewq_path, "--help"], capture_output=True, text=True, timeout=20.0)
    return Result("installed shim", proc.returncode == 0, proc.stdout + proc.stderr)


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
