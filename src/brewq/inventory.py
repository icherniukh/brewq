from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from brewq.model import Package


def formula_binaries(name: str) -> list[str]:
    """Return sorted binary names from the installed formula's bin/ directory."""
    simple = name.split("/")[-1]
    for prefix in ("/opt/homebrew/opt", "/usr/local/opt"):
        bin_dir = Path(f"{prefix}/{simple}/bin")
        if bin_dir.exists():
            try:
                return sorted(f.name for f in bin_dir.iterdir())
            except OSError:
                pass
    return []


@dataclass(frozen=True)
class InstalledRecord:
    name: str
    type: str
    version: str


def _directories(path: Path) -> list[Path]:
    try:
        return [entry for entry in path.iterdir() if entry.is_dir()]
    except OSError:
        return []


def _formula_record(formula_dir: Path) -> tuple[int, InstalledRecord] | None:
    candidates: list[tuple[int, InstalledRecord]] = []
    for version_dir in _directories(formula_dir):
        receipt = version_dir / "INSTALL_RECEIPT.json"
        try:
            raw = json.loads(receipt.read_text())
            installed_at = int(raw["time"])
            tap = str(raw["source"]["tap"])
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            continue
        name = formula_dir.name if tap == "homebrew/core" else f"{tap}/{formula_dir.name}"
        candidates.append((installed_at, InstalledRecord(name, "formula", version_dir.name)))
    return max(candidates, key=lambda candidate: candidate[0], default=None)


def _cask_record(cask_dir: Path) -> InstalledRecord | None:
    versions = [entry for entry in _directories(cask_dir) if not entry.name.startswith(".")]
    try:
        newest = max(versions, key=lambda entry: entry.stat().st_mtime)
    except (OSError, ValueError):
        return None
    return InstalledRecord(cask_dir.name, "cask", newest.name)


def scan(cellar: Path, caskroom: Path) -> dict[tuple[str, str], InstalledRecord]:
    records: dict[tuple[str, str], InstalledRecord] = {}
    for formula_dir in _directories(cellar):
        candidate = _formula_record(formula_dir)
        if candidate is not None:
            record = candidate[1]
            records[(record.type, record.name)] = record
    for cask_dir in _directories(caskroom):
        record = _cask_record(cask_dir)
        if record is not None:
            records[(record.type, record.name)] = record
    return records


def overlay(
    packages: list[Package],
    records: Mapping[tuple[str, str], InstalledRecord],
) -> None:
    for package in packages:
        record = records.get((package.type, package.name))
        if record is None:
            continue
        package.installed = True
        package.version = record.version
        if package.type == "formula":
            package.binaries = formula_binaries(package.name)
