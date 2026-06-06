from __future__ import annotations

import json
from pathlib import Path

import pytest

from brewq.model import Package, from_formula, from_cask

FIXTURES = Path(__file__).parent

@pytest.fixture
def formula_raw():
    data = json.loads((FIXTURES / "fixtures_brew_info.json").read_text())
    return data["formulae"][0]  # ripgrep

@pytest.fixture
def cask_raw():
    data = json.loads((FIXTURES / "fixtures_brew_casks.json").read_text())
    return data["casks"][0]  # raycast


def test_from_formula_basic(formula_raw):
    pkg = from_formula(formula_raw)
    assert pkg.name == "ripgrep"
    assert pkg.type == "formula"
    assert pkg.description == "Search tool like grep and The Silver Searcher"
    assert pkg.installs_30d == -1
    assert pkg.installs_365d == -1
    assert pkg.installed is True  # ripgrep is installed in fixture
    assert pkg.deprecated is False
    assert pkg.disabled is False
    assert "rg" in pkg.aliases


def test_from_formula_with_analytics(formula_raw):
    pkg = from_formula(formula_raw, installs_30d=50_000, installs_365d=600_000)
    assert pkg.installs_30d == 50_000
    assert pkg.installs_365d == 600_000
    assert pkg.installs == 50_000  # default metric is 30d


def test_from_cask_basic(cask_raw):
    pkg = from_cask(cask_raw)
    assert pkg.type == "cask"
    assert pkg.name == cask_raw["token"]
    assert pkg.description


def test_status_property():
    pkg = Package(
        name="x", type="formula", description="", url="", version="",
        installs_30d=-1, installs_365d=-1, installed=False,
        deprecated=True, disabled=False,
    )
    assert pkg.status == "deprecated"

    pkg2 = Package(
        name="x", type="formula", description="", url="", version="",
        installs_30d=-1, installs_365d=-1, installed=False,
        deprecated=False, disabled=True,
    )
    assert pkg2.status == "disabled"
