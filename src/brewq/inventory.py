from __future__ import annotations

import json
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


def scan(cellar: Path, caskroom: Path) -> InventoryScan:
    records: dict[tuple[str, str], InstalledRecord] = {}
    complete_types: set[str] = set()

    formula_dirs, formulae_complete = _directories(cellar)
    for formula_dir in formula_dirs:
        candidate, record_complete = _formula_record(formula_dir)
        formulae_complete = formulae_complete and record_complete
        if candidate is not None:
            record = candidate[1]
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
