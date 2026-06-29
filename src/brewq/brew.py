from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


def _brew_path() -> str:
    path = shutil.which("brew")
    if not path:
        raise FileNotFoundError(
            "brew not found. Install Homebrew from https://brew.sh"
        )
    return path


def info_all(timeout: float | None = None) -> dict[str, Any]:
    """Return parsed output of `brew info --json=v2 --eval-all`."""
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "check": True,
    }
    if timeout is not None:
        kwargs["timeout"] = timeout
    result = subprocess.run(
        [_brew_path(), "info", "--json=v2", "--eval-all"],
        **kwargs,
    )
    return json.loads(result.stdout)


def storage_roots() -> tuple[Path, Path]:
    """Return Homebrew's formula and cask installation roots."""
    brew = _brew_path()
    roots = []
    for flag in ("--cellar", "--caskroom"):
        result = subprocess.run(
            [brew, flag],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        roots.append(Path(result.stdout.strip()))
    return roots[0], roots[1]
