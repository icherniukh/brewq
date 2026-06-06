from __future__ import annotations

import fcntl
import json
import os
import time
from pathlib import Path
from typing import Any

from brewq import analytics as analytics_mod
from brewq import brew as brew_mod
from brewq import config as config_mod
from brewq.model import Package, from_cask, from_formula

_CACHE_FILE = "brew-all.json"
_LOCK_FILE = "refresh.lock"
_SCHEMA_VERSION = 1


def _dir() -> Path:
    return config_mod.cache_dir()


def cache_path() -> Path:
    return _dir() / _CACHE_FILE


def lock_path() -> Path:
    return _dir() / _LOCK_FILE


def _age_seconds() -> float | None:
    p = cache_path()
    if not p.exists():
        return None
    return time.time() - p.stat().st_mtime


def is_stale(max_age: int) -> bool:
    age = _age_seconds()
    if age is None:
        return True
    return age >= max_age


def status() -> dict[str, Any]:
    age = _age_seconds()
    locked = lock_path().exists()
    data: dict[str, Any] = {
        "path": str(cache_path()),
        "exists": age is not None,
        "age_seconds": int(age) if age is not None else None,
        "locked": locked,
        "formula_count": 0,
        "cask_count": 0,
        "has_analytics": False,
    }
    if age is not None:
        try:
            raw = json.loads(cache_path().read_text())
            data["formula_count"] = len(raw.get("formulae", []))
            data["cask_count"] = len(raw.get("casks", []))
            sample = raw.get("formulae", raw.get("casks", [{}]))
            if sample:
                data["has_analytics"] = sample[0].get("installs_30d", -1) != -1
        except (json.JSONDecodeError, OSError):
            pass
    return data


def refresh(force: bool = False, max_age: int | None = None) -> None:
    cfg = config_mod.load()
    if max_age is None:
        max_age = cfg["cache"]["max_age_seconds"]

    if not force and not is_stale(max_age):
        return

    d = _dir()
    d.mkdir(parents=True, exist_ok=True)

    lock = lock_path()
    lock_fh = open(lock, "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock_fh.close()
        return  # another process is refreshing

    try:
        _do_refresh(d)
    finally:
        fcntl.flock(lock_fh, fcntl.LOCK_UN)
        lock_fh.close()
        lock.unlink(missing_ok=True)


def _do_refresh(d: Path) -> None:
    brew_data = brew_mod.info_all()
    try:
        all_analytics = analytics_mod.fetch_all()
        analytics_mod.merge_into_brew_data(brew_data, all_analytics)
    except Exception:
        pass  # analytics are best-effort; write cache without them

    tmp = d / (_CACHE_FILE + ".tmp")
    tmp.write_text(json.dumps(brew_data))
    os.replace(tmp, d / _CACHE_FILE)  # atomic on POSIX


def clear() -> None:
    p = cache_path()
    if p.exists():
        p.unlink()


def load_packages() -> list[Package]:
    p = cache_path()
    if not p.exists():
        return []
    raw = json.loads(p.read_text())
    packages: list[Package] = []
    for f in raw.get("formulae", []):
        packages.append(from_formula(
            f,
            installs_30d=f.get("installs_30d", -1),
            installs_365d=f.get("installs_365d", -1),
        ))
    for c in raw.get("casks", []):
        packages.append(from_cask(
            c,
            installs_30d=c.get("installs_30d", -1),
            installs_365d=c.get("installs_365d", -1),
        ))
    return packages


def refresh_background(max_age: int | None = None) -> None:
    """Trigger a background cache refresh (non-blocking)."""
    cfg = config_mod.load()
    if max_age is None:
        max_age = cfg["cache"]["max_age_seconds"]
    if not is_stale(max_age):
        return
    pid = os.fork()
    if pid == 0:
        # child: detach and refresh
        os.setsid()
        try:
            refresh(force=True)
        except Exception:
            pass
        os._exit(0)
