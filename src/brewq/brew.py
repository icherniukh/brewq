from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


class BrewCommandError(RuntimeError):
    """A failed Homebrew query with a user-facing reason."""


def _brew_path() -> str:
    path = shutil.which("brew")
    if not path:
        raise FileNotFoundError(
            "brew not found. Install Homebrew from https://brew.sh"
        )
    return path


def _failure_reason(exc: subprocess.CalledProcessError) -> str:
    output = exc.stderr or exc.stdout or ""
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if lines:
        return next((line for line in lines if line.lower().startswith("error:")), lines[0])
    return f"exited with status {exc.returncode}"


def _run_brew(*args: str, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    command = [_brew_path(), *args]
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "check": True,
    }
    if timeout is not None:
        kwargs["timeout"] = timeout
    try:
        return subprocess.run(command, **kwargs)
    except subprocess.CalledProcessError as exc:
        operation = " ".join(args[:1]) or "command"
        raise BrewCommandError(
            f"brew {operation} failed: {_failure_reason(exc)}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        operation = " ".join(args[:1]) or "command"
        raise BrewCommandError(
            f"brew {operation} timed out after {exc.timeout:g}s"
        ) from exc


def info_all(timeout: float | None = None) -> dict[str, Any]:
    """Return parsed output of `brew info --json=v2` for trusted taps."""
    result = _run_brew("info", "--json=v2", timeout=timeout)
    return json.loads(result.stdout)


def storage_roots() -> tuple[Path, Path]:
    """Return Homebrew's formula and cask installation roots."""
    roots = []
    for flag in ("--cellar", "--caskroom"):
        result = _run_brew(flag, timeout=5)
        roots.append(Path(result.stdout.strip()))
    return roots[0], roots[1]
