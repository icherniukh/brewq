from __future__ import annotations

import json
from pathlib import Path

import pytest

from brewq.model import Package, from_cask, from_formula

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
    pkg = from_formula(formula_raw, installs_30d=50_000, installs_90d=150_000, installs_365d=600_000)
    assert pkg.installs_30d == 50_000
    assert pkg.installs_90d == 150_000
    assert pkg.installs_365d == 600_000


def test_from_cask_basic(cask_raw):
    pkg = from_cask(cask_raw)
    assert pkg.type == "cask"
    assert pkg.name == cask_raw["token"]
    assert pkg.description


def test_status_property():
    pkg = Package(
        name="x", type="formula", description="", url="", version="",
        installs_30d=-1, installs_90d=-1, installs_365d=-1, installed=False,
        deprecated=True, disabled=False,
    )
    assert pkg.status == "deprecated"

    pkg2 = Package(
        name="x", type="formula", description="", url="", version="",
        installs_30d=-1, installs_90d=-1, installs_365d=-1, installed=False,
        deprecated=False, disabled=True,
    )
    assert pkg2.status == "disabled"


def _pkg(installs_30d: int, installs_90d: int, installs_365d: int) -> Package:
    return Package(
        name="x", type="formula", description="", url="", version="",
        installs_30d=installs_30d, installs_90d=installs_90d, installs_365d=installs_365d,
        installed=False, deprecated=False, disabled=False,
    )


def test_trending_none_without_any_analytics():
    assert _pkg(-1, -1, -1).trending is None


def test_trending_none_with_only_recent_window():
    assert _pkg(500, -1, -1).trending is None


def test_trending_above_one_when_recent_rate_exceeds_history():
    pkg = _pkg(installs_30d=5_000, installs_90d=6_000, installs_365d=6_500)
    assert pkg.trending is not None
    assert pkg.trending > 1.0


def test_trending_below_one_when_recent_rate_falls_below_history():
    pkg = _pkg(installs_30d=50, installs_90d=600, installs_365d=3_000)
    assert pkg.trending is not None
    assert pkg.trending < 1.0


def test_trending_uses_pseudocount_when_baseline_is_zero():
    # A brand-new package with zero measurable history shouldn't be hidden as
    # None — the pseudocount still yields a meaningful "how hot right now" value.
    pkg = _pkg(installs_30d=100, installs_90d=100, installs_365d=100)
    assert pkg.trending == pytest.approx(1.3703703703703705)


def test_trending_new_to_tracking_is_damped_more_than_established_growth():
    # Same underlying recent-vs-older-window growth ratio (~2x) in both cases,
    # but "fresh" has almost no installs before its most recent 90d window (a
    # package new to analytics tracking, or a burst entirely within the last
    # 30 days -- see brewq-253's bun ~250x case) while "established" has a
    # much larger pre-90d install count. The maturity penalty should pull
    # "fresh" much closer to neutral (1.0x) than "established".
    fresh = _pkg(installs_30d=65, installs_90d=65, installs_365d=165)  # pre-90d=100
    established = _pkg(installs_30d=3_273, installs_90d=3_273, installs_365d=8_273)  # pre-90d=5,000
    assert fresh.trending is not None
    assert established.trending is not None
    assert abs(fresh.trending - 1.0) < abs(established.trending - 1.0)


def test_trending_falls_back_to_90d_only_history():
    pkg = _pkg(installs_30d=100, installs_90d=200, installs_365d=-1)
    assert pkg.trending is not None


def test_trending_falls_back_to_365d_only_history():
    pkg = _pkg(installs_30d=100, installs_90d=-1, installs_365d=1_000)
    assert pkg.trending is not None


def test_trending_low_volume_is_damped_toward_neutral():
    # Same underlying growth ratio (~2x recent vs. baseline), scaled up 1000x for
    # the high-volume case, to isolate the pseudocount-smoothing effect. 1.0 is
    # neutral under the new multiplier scale, so "damped" means pulled toward 1.0.
    low_volume = _pkg(installs_30d=10, installs_90d=20, installs_365d=66)
    high_volume = _pkg(installs_30d=10_000, installs_90d=20_000, installs_365d=66_000)
    assert abs(low_volume.trending - 1.0) < abs(high_volume.trending - 1.0)


def test_trending_has_no_hard_ceiling():
    pkg = _pkg(installs_30d=1_000_000, installs_90d=1_000_001, installs_365d=1_000_002)
    assert pkg.trending > 1000
