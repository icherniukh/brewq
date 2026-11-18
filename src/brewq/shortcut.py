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


def _unchanged(reason: str, dry_run: bool) -> str:
    verb = "would leave bq unchanged" if dry_run else "bq left unchanged"
    return f"{verb}: {reason}"


def path_block(found: str | None, brewq: Path, state: Path, *, dry_run: bool = False) -> str | None:
    """A foreign bq earlier on PATH must hide nothing and must not be replaced."""
    if not found:
        return None
    path = Path(found)
    if owned(path, brewq, _read(state)):
        return None
    return _unchanged(f"{path} is not brewq's shortcut", dry_run)


def ensure(brewq: Path, bindir: Path, state: Path, claim: str, *, dry_run: bool = False) -> str:
    """Link bq beside brewq, or explain why not. Does not create brq."""
    path = bindir / SHORTCUT
    record = _read(state)
    if claim in {"alias", "function", "reserved", "builtin", "unknown"}:
        return _unchanged(f"shell {claim}; use brewq", dry_run)
    if (path.exists() or path.is_symlink()) and not owned(path, brewq, record):
        return _unchanged(f"{path} is not brewq's shortcut", dry_run)
    if dry_run:
        return f"would link bq -> {brewq}"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or path.exists():
        path.unlink()
    path.symlink_to(brewq)
    _write(state, {"path": str(path), "target": str(brewq)})
    return f"bq -> {brewq}"


def remove(brewq: Path, bindir: Path, state: Path, *, dry_run: bool = False) -> str:
    path = bindir / SHORTCUT
    record = _read(state)
    if not path.is_symlink() and not path.exists():
        if dry_run:
            if state.exists():
                return "would remove bq shortcut state"
            return "bq shortcut absent"
        state.unlink(missing_ok=True)
        return "bq shortcut absent"
    if not owned(path, brewq, record):
        return _unchanged(f"{path} is not brewq's shortcut", dry_run)
    if dry_run:
        return "would remove bq shortcut"
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
