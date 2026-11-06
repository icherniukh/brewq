"""Collision-checked `bq` shortcut. Never overwrites a foreign command."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

SHORTCUT = "bq"


def same_tool(path: Path, brewq: Path) -> bool:
    """True when path is the uv-managed bq script beside this brewq install."""
    try:
        candidate = path.resolve()
        command = brewq.resolve()
    except OSError:
        return False
    return candidate.parent == command.parent and candidate.name == SHORTCUT and command.name == "brewq"


def owned(path: Path, brewq: Path, record: dict | None) -> bool:
    if not path.is_symlink():
        return False
    try:
        if path.resolve() == brewq.resolve() or same_tool(path, brewq):
            return True
    except OSError:
        pass
    return bool(record and record.get("path") == str(path) and path.readlink() == Path(record["target"]))


def shell_claim(name: str) -> str:
    """Return alias, function, command, absent, or unknown for the supported shell."""
    if not shutil_which("zsh"):
        return "unknown"
    try:
        proc = subprocess.run(
            ["zsh", "-ic", f"whence -w {name}"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    text = (proc.stdout or proc.stderr).strip().lower()
    if "not found" in text or text.endswith(": none") or text == "none":
        return "absent"
    for kind in ("alias", "function", "reserved", "builtin"):
        if kind in text:
            return kind
    if "command" in text:
        return "command"
    return "unknown"


def shutil_which(name: str) -> str | None:
    from shutil import which
    return which(name)


def path_block(found: str | None, brewq: Path, state: Path) -> str | None:
    """A foreign bq earlier on PATH must hide nothing and must not be replaced."""
    if not found:
        return None
    path = Path(found)
    if owned(path, brewq, _read(state)):
        return None
    return f"bq left unchanged: {path} is not brewq's shortcut"


def ensure(brewq: Path, bindir: Path, state: Path, claim: str) -> str:
    """Link bq beside brewq, or explain why not. Does not create brq."""
    path = bindir / SHORTCUT
    record = _read(state)
    if claim in {"alias", "function", "reserved", "builtin", "unknown"}:
        return f"bq left unchanged: shell {claim}; use brewq"
    if path.exists() or path.is_symlink():
        if not owned(path, brewq, record):
            return f"bq left unchanged: {path} is not brewq's shortcut"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or path.exists():
        path.unlink()
    path.symlink_to(brewq)
    _write(state, {"path": str(path), "target": str(brewq)})
    return f"bq -> {brewq}"


def remove(brewq: Path, bindir: Path, state: Path) -> str:
    path = bindir / SHORTCUT
    record = _read(state)
    if not path.is_symlink() and not path.exists():
        state.unlink(missing_ok=True)
        return "bq shortcut absent"
    if not owned(path, brewq, record):
        return f"bq left unchanged: {path} is not brewq's shortcut"
    path.unlink()
    state.unlink(missing_ok=True)
    return "bq shortcut removed"


def _read(state: Path) -> dict | None:
    try:
        data = json.loads(state.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write(state: Path, record: dict) -> None:
    state.parent.mkdir(parents=True, exist_ok=True)
    tmp = state.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, sort_keys=True) + "\n")
    os.replace(tmp, state)
