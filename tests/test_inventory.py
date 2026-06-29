from __future__ import annotations

import json
import os
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from brewq import brew
from brewq.inventory import InstalledRecord, overlay, scan
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
    _receipt(cellar / "ripgrep" / "14.0" / "INSTALL_RECEIPT.json", installed_at=10, tap="homebrew/core")
    _receipt(cellar / "ripgrep" / "15.0" / "INSTALL_RECEIPT.json", installed_at=20, tap="homebrew/core")
    _receipt(cellar / "widget" / "2.0" / "INSTALL_RECEIPT.json", installed_at=30, tap="acme/tools")

    records = scan(cellar, caskroom)

    assert records[("formula", "ripgrep")].version == "15.0"
    assert records[("formula", "acme/tools/widget")].version == "2.0"


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

    records = scan(cellar, tmp_path / "Caskroom")

    assert records[("cask", "firefox")].version == "125.0"


def test_scan_skips_malformed_receipt_without_losing_other_records(tmp_path):
    cellar = tmp_path / "Cellar"
    bad = cellar / "broken" / "1.0" / "INSTALL_RECEIPT.json"
    bad.parent.mkdir(parents=True)
    bad.write_text("not json")
    _receipt(cellar / "ripgrep" / "15.0" / "INSTALL_RECEIPT.json", installed_at=20, tap="homebrew/core")

    records = scan(cellar, tmp_path / "Caskroom")

    assert ("formula", "broken") not in records
    assert ("formula", "ripgrep") in records


def test_overlay_updates_only_matching_type_and_name():
    formula = _package("ripgrep", "formula")
    same_name_cask = _package("ripgrep", "cask")
    records = {
        ("formula", "ripgrep"): InstalledRecord("ripgrep", "formula", "15.0"),
    }

    overlay([formula, same_name_cask], records)

    assert formula.installed is True
    assert formula.version == "15.0"
    assert same_name_cask.installed is False
    assert same_name_cask.version == "seed"


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
