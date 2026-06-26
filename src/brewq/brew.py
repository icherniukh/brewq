from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any


def _brew_path() -> str:
    path = shutil.which("brew")
    if not path:
        raise FileNotFoundError(
            "brew not found. Install Homebrew from https://brew.sh"
        )
    return path


def info_all() -> dict[str, Any]:
    """Return parsed output of `brew info --json=v2 --eval-all`."""
    result = subprocess.run(
        [_brew_path(), "info", "--json=v2", "--eval-all"],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)
