from __future__ import annotations

import fcntl
import json
import os
import pickle
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, BinaryIO, Literal, TextIO

from brewq import analytics as analytics_mod
from brewq import brew as brew_mod
from brewq import config as config_mod
from brewq import inventory as inventory_mod
from brewq import seed as seed_mod
from brewq.model import Package, from_cask, from_formula

_CACHE_FILE = "brew-all.json"
_PICKLE_FILE = "brew-all.pkl"
_INVENTORY_INDEX_FILE = "inventory-index.pkl"
_CACHE_METADATA = "_brewq_cache"
_CACHE_SCHEMA = 1
_PICKLE_SCHEMA = 2
_LOCK_FILE = "refresh.lock"
_METRICS = ("installs_30d", "installs_90d", "installs_365d")


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
    analytics_complete: bool = True
    repair_needed: bool = False

    @property
    def requires_refresh(self) -> bool:
        return self.source == "seed" or self.repair_needed


@dataclass(frozen=True)
class _Snapshot:
    raw: dict[str, Any]
    analytics_complete: bool
    repair_needed: bool


def _dir() -> Path:
    return config_mod.cache_dir()


def cache_path() -> Path:
    return _dir() / _CACHE_FILE


def lock_path() -> Path:
    return _dir() / _LOCK_FILE


def pickle_path() -> Path:
    return _dir() / _PICKLE_FILE


@contextmanager
def _temporary_file(path: Path, mode: Literal["w", "wb"]) -> Iterator[TextIO | BinaryIO]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode=mode,
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    )
    tmp = Path(handle.name)
    try:
        yield handle
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        os.replace(tmp, path)
    except BaseException:
        handle.close()
        tmp.unlink(missing_ok=True)
        raise


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    with _temporary_file(path, "w") as handle:
        json.dump(payload, handle)


def _write_pickle(
    path: Path,
    packages: list[Package],
    storage_roots: tuple[str, str] | None,
    *,
    analytics_complete: bool,
    repair_needed: bool,
) -> None:
    payload = {
        "schema": _PICKLE_SCHEMA,
        "packages": packages,
        "storage_roots": storage_roots,
        "analytics_complete": analytics_complete,
        "repair_needed": repair_needed,
    }
    with _temporary_file(path, "wb") as handle:
        pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)


def _load_pickle(path: Path) -> dict[str, Any]:
    with open(path, "rb") as fh:
        payload = pickle.load(fh)
    if not isinstance(payload, dict):
        raise ValueError("pickle payload is not a dict")
    if payload.get("schema") != _PICKLE_SCHEMA:
        raise ValueError(f"pickle schema mismatch: {payload.get('schema')}")
    if not isinstance(payload.get("packages"), list):
        raise ValueError("pickle payload missing packages list")
    if type(payload.get("analytics_complete")) is not bool:
        raise ValueError("pickle payload missing analytics completeness")
    if type(payload.get("repair_needed")) is not bool:
        raise ValueError("pickle payload missing repair state")
    return payload


def _validate_optional_string(record: dict[str, Any], key: str, context: str) -> None:
    value = record.get(key)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{context} {key} is not a string")


def _validate_record(record: object, group: str, index: int) -> dict[str, Any]:
    context = f"{group}[{index}]"
    if not isinstance(record, dict):
        raise ValueError(f"{context} is not an object")
    identity = "name" if group == "formulae" else "token"
    if not isinstance(record.get(identity), str) or not record[identity]:
        raise ValueError(f"{context} has no valid {identity}")
    for key in ("desc", "homepage"):
        _validate_optional_string(record, key, context)
    for metric in _METRICS:
        value = record.get(metric)
        if value is not None and (type(value) is not int or value < -1):
            raise ValueError(f"{context} {metric} is not an integer")
    if group == "formulae":
        _validate_optional_string(record, "full_name", context)
        versions = record.get("versions")
        if versions is not None and not isinstance(versions, dict):
            raise ValueError(f"{context} versions is not an object")
        if versions is not None:
            _validate_optional_string(versions, "stable", f"{context} versions")
        installed = record.get("installed")
        if installed is not None and not isinstance(installed, list):
            raise ValueError(f"{context} installed is not an array")
        if installed:
            if not isinstance(installed[0], dict):
                raise ValueError(f"{context} installed contains a non-object record")
            _validate_optional_string(installed[0], "version", f"{context} installed[0]")
        aliases = record.get("aliases")
        if aliases is not None and (
            not isinstance(aliases, list) or any(not isinstance(alias, str) for alias in aliases)
        ):
            raise ValueError(f"{context} aliases is not an array of strings")
    else:
        _validate_optional_string(record, "version", context)
        _validate_optional_string(record, "installed", context)
        artifacts = record.get("artifacts")
        if artifacts is not None and not isinstance(artifacts, list):
            raise ValueError(f"{context} artifacts is not an array")
    return record


def _validate_snapshot(raw: object) -> _Snapshot:
    if not isinstance(raw, dict):
        raise ValueError("cache root is not an object")
    groups: dict[str, list[dict[str, Any]]] = {}
    for group in ("formulae", "casks"):
        records = raw.get(group)
        if not isinstance(records, list):
            raise ValueError(f"cache {group} is not an array")
        groups[group] = [_validate_record(record, group, index) for index, record in enumerate(records)]
    if not groups["formulae"] and not groups["casks"]:
        raise ValueError("cache catalog is empty")

    metadata = raw.get(_CACHE_METADATA)
    if metadata is None:
        return _Snapshot(raw, analytics_complete=False, repair_needed=True)
    if not isinstance(metadata, dict):
        raise ValueError("cache metadata is not an object")
    if metadata.get("schema_version") != _CACHE_SCHEMA:
        raise ValueError(f"unsupported cache schema: {metadata.get('schema_version')}")
    analytics_complete = metadata.get("analytics_complete")
    repair_needed = metadata.get("repair_needed")
    if type(analytics_complete) is not bool or type(repair_needed) is not bool:
        raise ValueError("cache metadata lacks completeness or repair state")
    if analytics_complete == repair_needed:
        raise ValueError("cache metadata has contradictory completeness state")
    return _Snapshot(raw, analytics_complete, repair_needed)


def _read_snapshot(path: Path) -> _Snapshot:
    return _validate_snapshot(json.loads(path.read_text()))


def _snapshot_metadata(*, analytics_complete: bool, repair_needed: bool) -> dict[str, Any]:
    return {
        "schema_version": _CACHE_SCHEMA,
        "analytics_complete": analytics_complete,
        "repair_needed": repair_needed,
    }


def age_seconds() -> float | None:
    path = cache_path()
    if not path.exists():
        return None
    return time.time() - path.stat().st_mtime


def is_stale(max_age: int) -> bool:
    age = age_seconds()
    if age is None:
        return True
    return age >= max_age


def _lock_is_held(path: Path) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as lock_fh:
        try:
            fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(lock_fh, fcntl.LOCK_UN)
    return False


def status() -> dict[str, Any]:
    age = age_seconds()
    data: dict[str, Any] = {
        "path": str(cache_path()),
        "exists": age is not None,
        "age_seconds": int(age) if age is not None else None,
        "locked": _lock_is_held(lock_path()),
        "formula_count": 0,
        "cask_count": 0,
        "has_analytics": False,
        "analytics_complete": False,
        "repair_needed": age is not None,
    }
    if age is not None:
        try:
            snapshot = _read_snapshot(cache_path())
            data["formula_count"] = len(snapshot.raw["formulae"])
            data["cask_count"] = len(snapshot.raw["casks"])
            data["has_analytics"] = any(
                any(record.get(metric, -1) >= 0 for metric in _METRICS)
                for group in ("formulae", "casks")
                for record in snapshot.raw[group]
            )
            data["analytics_complete"] = snapshot.analytics_complete
            data["repair_needed"] = snapshot.repair_needed
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            pass
    return data


def _healthy_fresh_snapshot(max_age: int) -> bool:
    if is_stale(max_age):
        return False
    try:
        snapshot = _read_snapshot(cache_path())
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return False
    return not snapshot.repair_needed


def refresh(force: bool = False, max_age: int | None = None) -> RefreshResult:
    cfg = config_mod.load()
    if max_age is None:
        max_age = cfg["cache"]["max_age_seconds"]
    if not force and _healthy_fresh_snapshot(max_age):
        return RefreshResult(RefreshOutcome.FRESH, cache_path())

    directory = _dir()
    directory.mkdir(parents=True, exist_ok=True)
    with lock_path().open("a+") as lock_fh:
        try:
            fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return RefreshResult(RefreshOutcome.LOCKED, cache_path())
        try:
            if not force and _healthy_fresh_snapshot(max_age):
                return RefreshResult(RefreshOutcome.FRESH, cache_path())
            return _do_refresh(directory)
        finally:
            fcntl.flock(lock_fh, fcntl.LOCK_UN)


def _retain_analytics(fresh: dict[str, Any], previous: dict[str, Any]) -> None:
    identities = {"formulae": "name", "casks": "token"}
    for group, identity in identities.items():
        old_records: dict[str, dict[str, Any]] = {}
        for record in previous[group]:
            key = record.get("full_name") if group == "formulae" else record.get(identity)
            key = key or record.get(identity)
            if isinstance(key, str):
                old_records[key] = record
        for record in fresh[group]:
            key = record.get("full_name") if group == "formulae" else record.get(identity)
            key = key or record.get(identity)
            old = old_records.get(key)
            if old is None:
                continue
            for metric in _METRICS:
                value = old.get(metric)
                if type(value) is int and value >= 0:
                    record[metric] = value


def _do_refresh(directory: Path) -> RefreshResult:
    brew_data = brew_mod.info_all()
    _validate_snapshot(brew_data)

    analytics_error = None
    try:
        all_analytics = analytics_mod.fetch_all()
        analytics_mod.merge_into_brew_data(brew_data, all_analytics)
    except analytics_mod.AnalyticsFetchError as exc:
        analytics_error = str(exc)
        try:
            previous = _read_snapshot(cache_path())
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            pass
        else:
            _retain_analytics(brew_data, previous.raw)

    analytics_complete = analytics_error is None
    repair_needed = not analytics_complete
    brew_data[_CACHE_METADATA] = _snapshot_metadata(
        analytics_complete=analytics_complete,
        repair_needed=repair_needed,
    )
    snapshot = _validate_snapshot(brew_data)
    pickle_path().unlink(missing_ok=True)
    _write_json(directory / _CACHE_FILE, brew_data)

    try:
        packages = _packages_from_data(snapshot.raw)
        cellar, caskroom = brew_mod.storage_roots()
        _write_pickle(
            directory / _PICKLE_FILE,
            packages,
            (str(cellar), str(caskroom)),
            analytics_complete=snapshot.analytics_complete,
            repair_needed=snapshot.repair_needed,
        )
    except (OSError, ValueError):
        pass

    if analytics_error is not None:
        return RefreshResult(
            RefreshOutcome.METADATA_ONLY,
            directory / _CACHE_FILE,
            analytics_error=analytics_error,
        )
    return RefreshResult(RefreshOutcome.COMPLETE, directory / _CACHE_FILE)


def clear() -> None:
    directory = _dir()
    directory.mkdir(parents=True, exist_ok=True)
    with lock_path().open("a+") as lock_fh:
        fcntl.flock(lock_fh, fcntl.LOCK_EX)
        try:
            cache_path().unlink(missing_ok=True)
            pickle_path().unlink(missing_ok=True)
        finally:
            fcntl.flock(lock_fh, fcntl.LOCK_UN)


def _packages_from_data(raw: dict[str, Any]) -> list[Package]:
    packages: list[Package] = []
    for formula in raw["formulae"]:
        packages.append(from_formula(
            formula,
            installs_30d=formula.get("installs_30d", -1),
            installs_90d=formula.get("installs_90d", -1),
            installs_365d=formula.get("installs_365d", -1),
        ))
    for cask in raw["casks"]:
        packages.append(from_cask(
            cask,
            installs_30d=cask.get("installs_30d", -1),
            installs_90d=cask.get("installs_90d", -1),
            installs_365d=cask.get("installs_365d", -1),
        ))
    return packages


def _overlay_inventory(packages: list[Package], roots: object = None) -> tuple[str, str] | None:
    try:
        if roots is None:
            cellar, caskroom = brew_mod.storage_roots()
        else:
            if not isinstance(roots, (tuple, list)) or len(roots) != 2:
                raise ValueError("invalid cached storage roots")
            cellar, caskroom = Path(roots[0]), Path(roots[1])
        scan_result = inventory_mod.scan(cellar, caskroom, _dir() / _INVENTORY_INDEX_FILE)
        inventory_mod.overlay(packages, scan_result)
        return str(cellar), str(caskroom)
    except (OSError, ValueError):
        return None


def _load_user_cache(path: Path, current_time: float) -> CacheLoad | None:
    """Load one user snapshot while the caller holds the shared cache lock."""
    pickle_file = pickle_path()
    if pickle_file.exists() and pickle_file.stat().st_mtime >= path.stat().st_mtime:
        try:
            data = _load_pickle(pickle_file)
            packages = data["packages"]
            roots = _overlay_inventory(packages, data.get("storage_roots"))
            if roots is not None and data.get("storage_roots") is None:
                _write_pickle(
                    pickle_file,
                    packages,
                    roots,
                    analytics_complete=data["analytics_complete"],
                    repair_needed=data["repair_needed"],
                )
            return CacheLoad(
                source="user",
                packages=packages,
                age_seconds=max(0.0, current_time - path.stat().st_mtime),
                analytics_complete=data["analytics_complete"],
                repair_needed=data["repair_needed"],
            )
        except (OSError, ValueError, pickle.UnpicklingError, EOFError,
                AttributeError, TypeError, ImportError, KeyError):
            pass

    try:
        snapshot = _read_snapshot(path)
        packages = _packages_from_data(snapshot.raw)
        roots = _overlay_inventory(packages)
        try:
            _write_pickle(
                pickle_file,
                packages,
                roots,
                analytics_complete=snapshot.analytics_complete,
                repair_needed=snapshot.repair_needed,
            )
        except OSError:
            pass
        return CacheLoad(
            source="user",
            packages=packages,
            age_seconds=max(0.0, current_time - path.stat().st_mtime),
            analytics_complete=snapshot.analytics_complete,
            repair_needed=snapshot.repair_needed,
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(
            f"brewq: cache corrupt ({path}) — using bundled data; run 'brewq refresh' to recover ({exc})",
            file=sys.stderr,
        )
        return None


def load(now: float | None = None) -> CacheLoad:
    current_time = time.time() if now is None else now
    path = cache_path()
    if path.exists():
        # Readers share the refresh lock so an old JSON snapshot cannot produce
        # a newer pickle while refresh atomically replaces both representations.
        with lock_path().open("a+") as lock_fh:
            fcntl.flock(lock_fh, fcntl.LOCK_SH)
            try:
                loaded = _load_user_cache(path, current_time) if path.exists() else None
            finally:
                fcntl.flock(lock_fh, fcntl.LOCK_UN)
        if loaded is not None:
            return loaded

    raw, metadata = seed_mod.load_resource()
    packages = _packages_from_data(raw)
    _overlay_inventory(packages)
    return CacheLoad(
        source="seed",
        packages=packages,
        age_seconds=max(0.0, current_time - metadata.generated_at),
        analytics_complete=True,
        repair_needed=False,
    )


def load_packages() -> list[Package]:
    """Return packages from the user cache file only, without inventory overlay."""
    path = cache_path()
    if not path.exists():
        return []
    with lock_path().open("a+") as lock_fh:
        fcntl.flock(lock_fh, fcntl.LOCK_SH)
        try:
            if not path.exists():
                return []
            pickle_file = pickle_path()
            if pickle_file.exists() and pickle_file.stat().st_mtime >= path.stat().st_mtime:
                try:
                    return _load_pickle(pickle_file)["packages"]
                except (OSError, ValueError, pickle.UnpicklingError, EOFError,
                        AttributeError, TypeError, ImportError, KeyError):
                    pass
            snapshot = _read_snapshot(path)
            packages = _packages_from_data(snapshot.raw)
            try:
                _write_pickle(
                    pickle_file,
                    packages,
                    None,
                    analytics_complete=snapshot.analytics_complete,
                    repair_needed=snapshot.repair_needed,
                )
            except OSError:
                pass
            return packages
        finally:
            fcntl.flock(lock_fh, fcntl.LOCK_UN)


def foreground_bootstrap(timeout: float = 60) -> CacheLoad:
    directory = _dir()
    directory.mkdir(parents=True, exist_ok=True)
    with lock_path().open("a+") as lock_fh:
        fcntl.flock(lock_fh, fcntl.LOCK_EX)
        try:
            data = brew_mod.info_all(timeout=timeout)
            if not isinstance(data, dict):
                raise ValueError("Homebrew metadata root is not an object")
            data[_CACHE_METADATA] = _snapshot_metadata(
                analytics_complete=False,
                repair_needed=True,
            )
            snapshot = _validate_snapshot(data)
            pickle_path().unlink(missing_ok=True)
            _write_json(cache_path(), data)
        finally:
            fcntl.flock(lock_fh, fcntl.LOCK_UN)
    return CacheLoad(
        source="user",
        packages=_packages_from_data(snapshot.raw),
        age_seconds=0,
        analytics_complete=False,
        repair_needed=True,
    )
