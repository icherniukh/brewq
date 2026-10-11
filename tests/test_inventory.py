from __future__ import annotations

import json
import os
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from brewq import brew
from brewq.inventory import InstalledRecord, InventoryScan, overlay, scan
from brewq.model import Package


def _receipt(path: Path, *, installed_at: int, tap: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"time": installed_at, "source": {"tap": tap}}))


def _package(name: str, type_: str) -> Package:
    return Package(
        name=name,
        type=type_,
        description="",
        url="",
        version="seed",
        installs_30d=1,
        installs_90d=2,
        installs_365d=3,
        installed=False,
        deprecated=False,
        disabled=False,
    )


def test_scan_reconstructs_formula_names_and_selects_newest_receipt(tmp_path):
    cellar = tmp_path / "Cellar"
    caskroom = tmp_path / "Caskroom"
    caskroom.mkdir()
    _receipt(cellar / "ripgrep" / "14.0" / "INSTALL_RECEIPT.json", installed_at=10, tap="homebrew/core")
    _receipt(cellar / "ripgrep" / "15.0" / "INSTALL_RECEIPT.json", installed_at=20, tap="homebrew/core")
    _receipt(cellar / "widget" / "2.0" / "INSTALL_RECEIPT.json", installed_at=30, tap="acme/tools")

    inventory = scan(cellar, caskroom)

    assert inventory.records[("formula", "ripgrep")].version == "15.0"
    assert inventory.records[("formula", "acme/tools/widget")].version == "2.0"
    assert inventory.complete_types == {"formula", "cask"}


def test_scan_casks_ignores_metadata_and_selects_newest_version(tmp_path):
    cellar = tmp_path / "Cellar"
    cask = tmp_path / "Caskroom" / "firefox"
    old = cask / "124.0"
    new = cask / "125.0"
    metadata = cask / ".metadata"
    for path in (old, new, metadata):
        path.mkdir(parents=True)
    os.utime(old, (10, 10))
    os.utime(new, (20, 20))
    os.utime(metadata, (30, 30))

    inventory = scan(cellar, tmp_path / "Caskroom")

    assert inventory.records[("cask", "firefox")].version == "125.0"


def test_scan_skips_malformed_receipt_without_losing_other_records(tmp_path):
    cellar = tmp_path / "Cellar"
    bad = cellar / "broken" / "1.0" / "INSTALL_RECEIPT.json"
    bad.parent.mkdir(parents=True)
    bad.write_text("not json")
    _receipt(cellar / "ripgrep" / "15.0" / "INSTALL_RECEIPT.json", installed_at=20, tap="homebrew/core")

    inventory = scan(cellar, tmp_path / "Caskroom")

    assert ("formula", "broken") not in inventory.records
    assert ("formula", "ripgrep") in inventory.records
    assert "formula" not in inventory.complete_types


def test_overlay_updates_only_matching_type_and_name():
    formula = _package("ripgrep", "formula")
    same_name_cask = _package("ripgrep", "cask")
    inventory = InventoryScan(
        {("formula", "ripgrep"): InstalledRecord("ripgrep", "formula", "15.0")},
        frozenset({"formula", "cask"}),
    )

    overlay([formula, same_name_cask], inventory)

    assert formula.installed is True
    assert formula.version == "seed"
    assert formula.installed_version == "15.0"
    assert same_name_cask.installed is False
    assert same_name_cask.version == "seed"


def test_successful_empty_scan_clears_stale_installed_state(tmp_path):
    stale = _package("ripgrep", "formula")
    stale.installed = True
    stale.installed_version = "14.0"
    stale.binaries = ["rg"]
    cellar = tmp_path / "Cellar"
    caskroom = tmp_path / "Caskroom"
    cellar.mkdir()
    caskroom.mkdir()

    inventory = scan(cellar, caskroom)
    overlay([stale], inventory)

    assert stale.installed is False
    assert stale.installed_version == ""
    assert stale.binaries == []


def test_failed_scan_preserves_stale_installed_state(tmp_path, monkeypatch):
    stale = _package("ripgrep", "formula")
    stale.installed = True
    stale.installed_version = "14.0"

    def unreadable(path: Path):
        if path.name == "Cellar":
            raise PermissionError(path)
        return iter(())

    monkeypatch.setattr(Path, "iterdir", unreadable)
    inventory = scan(tmp_path / "Cellar", tmp_path / "Caskroom")
    overlay([stale], inventory)

    assert "formula" not in inventory.complete_types
    assert stale.installed is True
    assert stale.installed_version == "14.0"


def test_missing_root_preserves_stale_installed_state(tmp_path):
    stale = _package("ripgrep", "formula")
    stale.installed = True
    stale.installed_version = "14.0"

    inventory = scan(tmp_path / "missing-cellar", tmp_path / "missing-caskroom")
    overlay([stale], inventory)

    assert inventory.complete_types == set()
    assert stale.installed is True
    assert stale.installed_version == "14.0"


def test_inventory_only_package_is_added_with_unknown_catalog_metadata():
    packages: list[Package] = []
    inventory = InventoryScan(
        {("formula", "local-tool"): InstalledRecord(
            "local-tool", "formula", "2.1", ("local-tool",),
        )},
        frozenset({"formula", "cask"}),
    )

    overlay(packages, inventory)

    assert len(packages) == 1
    package = packages[0]
    assert package.name == "local-tool"
    assert package.version == ""
    assert package.installed_version == "2.1"
    assert package.description == ""
    assert package.url == ""
    assert package.installs_30d == -1
    assert package.installs_90d == -1
    assert package.installs_365d == -1
    assert package.binaries == ["local-tool"]


def test_formula_binaries_come_from_discovered_cellar(tmp_path):
    cellar = tmp_path / "custom" / "Cellar"
    version_dir = cellar / "ripgrep" / "15.0"
    _receipt(version_dir / "INSTALL_RECEIPT.json", installed_at=20, tap="homebrew/core")
    bin_dir = version_dir / "bin"
    bin_dir.mkdir()
    (bin_dir / "rg").touch()

    inventory = scan(cellar, tmp_path / "custom" / "Caskroom")

    assert inventory.records[("formula", "ripgrep")].binaries == ("rg",)


def test_storage_roots_uses_bounded_homebrew_queries():
    results = [
        CompletedProcess([], 0, stdout="/opt/homebrew/Cellar\n", stderr=""),
        CompletedProcess([], 0, stdout="/opt/homebrew/Caskroom\n", stderr=""),
    ]
    with patch("brewq.brew._brew_path", return_value="/opt/homebrew/bin/brew"), \
         patch("brewq.brew.subprocess.run", side_effect=results) as run:
        roots = brew.storage_roots()

    assert roots == (Path("/opt/homebrew/Cellar"), Path("/opt/homebrew/Caskroom"))
    assert [call.kwargs["timeout"] for call in run.call_args_list] == [5, 5]


def test_scan_index_reuses_unchanged_formulae_and_rescans_changed_ones(tmp_path):
    cellar = tmp_path / "Cellar"
    caskroom = tmp_path / "Caskroom"
    caskroom.mkdir()
    index = tmp_path / "index.pkl"
    _receipt(cellar / "ripgrep" / "14.0" / "INSTALL_RECEIPT.json", installed_at=10, tap="homebrew/core")
    _receipt(cellar / "jq" / "1.7" / "INSTALL_RECEIPT.json", installed_at=10, tap="homebrew/core")
    (cellar / "jq" / "1.7" / "bin").mkdir()
    (cellar / "jq" / "1.7" / "bin" / "jq").write_text("")

    first = scan(cellar, caskroom, index)
    assert index.exists()
    assert first.records[("formula", "jq")].binaries == ("jq",)

    with patch("brewq.inventory._formula_record", side_effect=AssertionError("rescanned")):
        second = scan(cellar, caskroom, index)
    assert second.records == first.records

    _receipt(cellar / "ripgrep" / "15.0" / "INSTALL_RECEIPT.json", installed_at=20, tap="homebrew/core")
    third = scan(cellar, caskroom, index)
    assert third.records[("formula", "ripgrep")].version == "15.0"
    assert third.records[("formula", "jq")].version == "1.7"


def test_scan_index_drops_removed_formulae_and_ignores_corrupt_index(tmp_path):
    cellar = tmp_path / "Cellar"
    caskroom = tmp_path / "Caskroom"
    caskroom.mkdir()
    index = tmp_path / "index.pkl"
    _receipt(cellar / "jq" / "1.7" / "INSTALL_RECEIPT.json", installed_at=10, tap="homebrew/core")
    scan(cellar, caskroom, index)

    index.write_bytes(b"not a pickle")
    assert ("formula", "jq") in scan(cellar, caskroom, index).records

    import shutil
    shutil.rmtree(cellar / "jq")
    assert ("formula", "jq") not in scan(cellar, caskroom, index).records
