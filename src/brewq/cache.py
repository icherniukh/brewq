from __future__ import annotations

import fcntl
import json
import os
import pickle
import sys
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from brewq import analytics as analytics_mod
from brewq import brew as brew_mod
from brewq import config as config_mod
from brewq import inventory as inventory_mod
from brewq import seed as seed_mod
from brewq.model import Package, from_cask, from_formula

_CACHE_FILE = "brew-all.json"
_PICKLE_FILE = "brew-all.pkl"
_PICKLE_SCHEMA = 1
_LOCK_FILE = "refresh.lock"


class RefreshOutcome(StrEnum):
    FRESH = "fresh"
    LOCKED = "locked"
    COMPLETE = "complete"
    METADATA_ONLY = "metadata_only"


@dataclass(frozen=True)
class RefreshResult:
    outcome: RefreshOutcome
    path: Path
    analytics_error: str | None = None


@dataclass(frozen=True)
class CacheLoad:
    source: Literal["user", "seed"]
    packages: list[Package]
    age_seconds: float
    requires_refresh: bool = False


def _dir() -> Path:
    return config_mod.cache_dir()


def cache_path() -> Path:
    return _dir() / _CACHE_FILE


def lock_path() -> Path:
    return _dir() / _LOCK_FILE


def pickle_path() -> Path:
    return _dir() / _PICKLE_FILE


def _write_pickle(path: Path, packages: list[Package], storage_roots: tuple[str, str] | None) -> None:
    payload = {"schema": _PICKLE_SCHEMA, "packages": packages, "storage_roots": storage_roots}
    tmp = path.parent / (path.name + ".tmp")
    with open(tmp, "wb") as fh:
        pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, path)


def _load_pickle(path: Path) -> dict[str, Any]:
    with open(path, "rb") as fh:
        payload = pickle.load(fh)
    if not isinstance(payload, dict):
        raise ValueError("pickle payload is not a dict")
    if payload.get("schema") != _PICKLE_SCHEMA:
        raise ValueError(f"pickle schema mismatch: {payload.get('schema')}")
    if not isinstance(payload.get("packages"), list):
        raise ValueError("pickle payload missing packages list")
    return payload


def age_seconds() -> float | None:
    p = cache_path()
    if not p.exists():
        return None
    return time.time() - p.stat().st_mtime


def is_stale(max_age: int) -> bool:
    age = age_seconds()
    if age is None:
        return True
    return age >= max_age


def status() -> dict[str, Any]:
    age = age_seconds()
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


def refresh(force: bool = False, max_age: int | None = None) -> RefreshResult:
    cfg = config_mod.load()
    if max_age is None:
        max_age = cfg["cache"]["max_age_seconds"]

    if not force and not is_stale(max_age):
        return RefreshResult(RefreshOutcome.FRESH, cache_path())

    d = _dir()
    d.mkdir(parents=True, exist_ok=True)

    lock = lock_path()
    lock_fh = open(lock, "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock_fh.close()
        return RefreshResult(RefreshOutcome.LOCKED, cache_path())

    try:
        return _do_refresh(d)
    finally:
        fcntl.flock(lock_fh, fcntl.LOCK_UN)
        lock_fh.close()
        lock.unlink(missing_ok=True)


def _do_refresh(d: Path) -> RefreshResult:
    brew_data = brew_mod.info_all()
    analytics_error = None
    try:
        all_analytics = analytics_mod.fetch_all()
        analytics_mod.merge_into_brew_data(brew_data, all_analytics)
    except analytics_mod.AnalyticsFetchError as exc:
        analytics_error = str(exc)

    tmp = d / (_CACHE_FILE + ".tmp")
    tmp.write_text(json.dumps(brew_data))
    os.replace(tmp, d / _CACHE_FILE)  # atomic on POSIX

    try:
        packages = _packages_from_data(brew_data)
        cellar, caskroom = brew_mod.storage_roots()
        _write_pickle(d / _PICKLE_FILE, packages, (str(cellar), str(caskroom)))
    except (OSError, ValueError):
        pass

    if analytics_error is not None:
        return RefreshResult(
            RefreshOutcome.METADATA_ONLY,
            d / _CACHE_FILE,
            analytics_error=analytics_error,
        )
    return RefreshResult(RefreshOutcome.COMPLETE, d / _CACHE_FILE)


def clear() -> None:
    p = cache_path()
    if p.exists():
        p.unlink()
    pickle_path().unlink(missing_ok=True)


def _packages_from_data(raw: dict[str, Any]) -> list[Package]:
    packages: list[Package] = []
    for f in raw.get("formulae", []):
        packages.append(from_formula(
            f,
            installs_30d=f.get("installs_30d", -1),
            installs_90d=f.get("installs_90d", -1),
            installs_365d=f.get("installs_365d", -1),
        ))
    for c in raw.get("casks", []):
        packages.append(from_cask(
            c,
            installs_30d=c.get("installs_30d", -1),
            installs_90d=c.get("installs_90d", -1),
            installs_365d=c.get("installs_365d", -1),
        ))
    return packages


def load(now: float | None = None) -> CacheLoad:
    current_time = time.time() if now is None else now
    p = cache_path()
    if p.exists():
        pkl = pickle_path()
        if pkl.exists() and pkl.stat().st_mtime >= p.stat().st_mtime:
            try:
                data = _load_pickle(pkl)
                packages = data["packages"]
                roots = data.get("storage_roots")
                if roots is not None:
                    cellar, caskroom = Path(roots[0]), Path(roots[1])
                else:
                    cellar, caskroom = brew_mod.storage_roots()
                    _write_pickle(pkl, packages, (str(cellar), str(caskroom)))
                records = inventory_mod.scan(cellar, caskroom)
                inventory_mod.overlay(packages, records)
                return CacheLoad(
                    source="user",
                    packages=packages,
                    age_seconds=max(0.0, current_time - p.stat().st_mtime),
                )
            except (OSError, ValueError, pickle.UnpicklingError, EOFError,
                    AttributeError, TypeError, ImportError, KeyError):
                pass

        try:
            raw = json.loads(p.read_text())
            if not isinstance(raw, dict):
                raise TypeError("cache root is not an object")
            packages = _packages_from_data(raw)
            try:
                cellar, caskroom = brew_mod.storage_roots()
                _write_pickle(pkl, packages, (str(cellar), str(caskroom)))
                records = inventory_mod.scan(cellar, caskroom)
                inventory_mod.overlay(packages, records)
            except (OSError, ValueError):
                pass
            return CacheLoad(
                source="user",
                packages=packages,
                age_seconds=max(0.0, current_time - p.stat().st_mtime),
            )
        except (OSError, TypeError, json.JSONDecodeError) as exc:
            print(
                f"brewq: cache corrupt ({p}) — using bundled data; run 'brewq refresh' to recover ({exc})",
                file=sys.stderr,
            )

    raw, metadata = seed_mod.load_resource()
    packages = _packages_from_data(raw)
    try:
        cellar, caskroom = brew_mod.storage_roots()
        records = inventory_mod.scan(cellar, caskroom)
        inventory_mod.overlay(packages, records)
    except (OSError, ValueError):
        pass
    return CacheLoad(
        source="seed",
        packages=packages,
        age_seconds=max(0.0, current_time - metadata.generated_at),
        requires_refresh=True,
    )


def load_packages() -> list[Package]:
    """Return packages from the user cache file only — no seed fallback, no installed-state overlay.
    Intended for benchmarks and isolated performance tests; not suitable for production code paths."""
    p = cache_path()
    if not p.exists():
        return []
    pkl = pickle_path()
    if pkl.exists() and pkl.stat().st_mtime >= p.stat().st_mtime:
        try:
            return _load_pickle(pkl)["packages"]
        except (OSError, ValueError, pickle.UnpicklingError, EOFError,
                AttributeError, TypeError, ImportError, KeyError):
            pass
    raw = json.loads(p.read_text())
    packages = _packages_from_data(raw)
    try:
        _write_pickle(pkl, packages, None)
    except OSError:
        pass
    return packages


def foreground_bootstrap(timeout: float = 60) -> CacheLoad:
    data = brew_mod.info_all(timeout=timeout)
    d = _dir()
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / (_CACHE_FILE + ".tmp")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, cache_path())
    pickle_path().unlink(missing_ok=True)
    return CacheLoad(
        source="user",
        packages=_packages_from_data(data),
        age_seconds=0,
        requires_refresh=True,
    )
