from __future__ import annotations

import json
import os
import pickle
import tempfile
from dataclasses import dataclass
from pathlib import Path

from brewq.model import Package


@dataclass(frozen=True)
class InstalledRecord:
    name: str
    type: str
    version: str
    binaries: tuple[str, ...] = ()


@dataclass(frozen=True)
class InventoryScan:
    records: dict[tuple[str, str], InstalledRecord]
    complete_types: frozenset[str]


def _directories(path: Path) -> tuple[list[Path], bool]:
    try:
        return [entry for entry in path.iterdir() if entry.is_dir()], True
    except OSError:
        return [], False


def _formula_binaries(version_dir: Path) -> tuple[tuple[str, ...], bool]:
    try:
        return tuple(sorted(entry.name for entry in (version_dir / "bin").iterdir())), True
    except FileNotFoundError:
        return (), True
    except OSError:
        return (), False


def _formula_record(formula_dir: Path) -> tuple[tuple[int, InstalledRecord] | None, bool]:
    candidates: list[tuple[int, InstalledRecord]] = []
    version_dirs, complete = _directories(formula_dir)
    for version_dir in version_dirs:
        receipt = version_dir / "INSTALL_RECEIPT.json"
        try:
            raw = json.loads(receipt.read_text())
            installed_at = int(raw["time"])
            tap = str(raw["source"]["tap"])
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            complete = False
            continue
        name = formula_dir.name if tap == "homebrew/core" else f"{tap}/{formula_dir.name}"
        binaries, binaries_complete = _formula_binaries(version_dir)
        complete = complete and binaries_complete
        candidates.append(
            (installed_at, InstalledRecord(name, "formula", version_dir.name, binaries))
        )
    return max(candidates, key=lambda candidate: candidate[0], default=None), complete


def _cask_record(cask_dir: Path) -> tuple[InstalledRecord | None, bool]:
    version_dirs, complete = _directories(cask_dir)
    versions = [entry for entry in version_dirs if not entry.name.startswith(".")]
    try:
        newest = max(versions, key=lambda entry: entry.stat().st_mtime)
    except (OSError, ValueError):
        return None, complete and not versions
    return InstalledRecord(cask_dir.name, "cask", newest.name), complete


_INDEX_SCHEMA = 1
# formula directory name -> (directory mtime_ns, newest installed candidate or None)
_Index = dict[str, tuple[int, tuple[int, InstalledRecord] | None]]


def _load_index(path: Path | None, cellar: Path) -> _Index:
    if path is None:
        return {}
    try:
        with open(path, "rb") as fh:
            payload = pickle.load(fh)
        if payload["schema"] == _INDEX_SCHEMA and payload["cellar"] == str(cellar):
            entries = payload["entries"]
            if isinstance(entries, dict):
                return entries
    except Exception:
        pass
    return {}


def _save_index(path: Path, cellar: Path, entries: _Index) -> None:
    payload = {"schema": _INDEX_SCHEMA, "cellar": str(cellar), "entries": entries}
    tmp_name = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as fh:
            tmp_name = fh.name
            pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp_name, path)
    except OSError:
        if tmp_name is not None:
            Path(tmp_name).unlink(missing_ok=True)


def _scan_formulae(cellar: Path, index_path: Path | None) -> tuple[list[InstalledRecord], bool]:
    """Scan the Cellar, reusing per-formula results while a directory's mtime is unchanged.

    Adding, removing, or reinstalling a keg changes its formula directory's mtime,
    so unchanged directories keep their previous receipt and binary listing.
    """
    previous = _load_index(index_path, cellar)
    current: _Index = {}
    records: list[InstalledRecord] = []
    complete = True
    try:
        entries = [e for e in os.scandir(cellar) if e.is_dir()]
    except OSError:
        return records, False
    for entry in entries:
        try:
            mtime = entry.stat().st_mtime_ns
        except OSError:
            complete = False
            continue
        cached = previous.get(entry.name)
        if cached is not None and cached[0] == mtime:
            candidate = cached[1]
            current[entry.name] = cached
        else:
            candidate, record_complete = _formula_record(Path(entry.path))
            if record_complete:
                current[entry.name] = (mtime, candidate)
            else:
                complete = False
        if candidate is not None:
            records.append(candidate[1])
    if index_path is not None and current != previous:
        _save_index(index_path, cellar, current)
    return records, complete


def scan(cellar: Path, caskroom: Path, index_path: Path | None = None) -> InventoryScan:
    records: dict[tuple[str, str], InstalledRecord] = {}
    complete_types: set[str] = set()

    formula_records, formulae_complete = _scan_formulae(cellar, index_path)
    for record in formula_records:
        records[(record.type, record.name)] = record
    if formulae_complete:
        complete_types.add("formula")

    cask_dirs, casks_complete = _directories(caskroom)
    for cask_dir in cask_dirs:
        record, record_complete = _cask_record(cask_dir)
        casks_complete = casks_complete and record_complete
        if record is not None:
            records[(record.type, record.name)] = record
    if casks_complete:
        complete_types.add("cask")

    return InventoryScan(records, frozenset(complete_types))


def overlay(
    packages: list[Package],
    inventory: InventoryScan,
) -> None:
    matched: set[tuple[str, str]] = set()
    for package in packages:
        key = (package.type, package.name)
        record = inventory.records.get(key)
        if record is None:
            if package.type in inventory.complete_types:
                package.installed = False
                package.installed_version = ""
                if package.type == "formula":
                    package.binaries = []
            continue
        matched.add(key)
        package.installed = True
        package.installed_version = record.version
        if package.type == "formula":
            package.binaries = list(record.binaries)

    for key, record in inventory.records.items():
        if key in matched:
            continue
        packages.append(Package(
            name=record.name,
            type=record.type,
            description="",
            url="",
            version="",
            installs_30d=-1,
            installs_90d=-1,
            installs_365d=-1,
            installed=True,
            deprecated=False,
            disabled=False,
            binaries=list(record.binaries),
            installed_version=record.version,
        ))
