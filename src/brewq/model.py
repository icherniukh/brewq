from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Package:
    """Normalized record for a formula or cask."""

    name: str
    type: str  # "formula" | "cask"
    description: str
    url: str
    version: str
    installs_30d: int   # -1 = unknown; sourced from install_on_request for formulae
    installs_90d: int   # -1 = unknown
    installs_365d: int  # -1 = unknown
    installed: bool
    deprecated: bool
    disabled: bool
    aliases: list[str] = field(default_factory=list)
    binaries: list[str] = field(default_factory=list)
    installed_version: str = ""

    @property
    def status(self) -> str:
        if self.disabled:
            return "disabled"
        if self.deprecated:
            return "deprecated"
        return ""

    # Added to both the recent and baseline monthly rate before dividing (Laplace/
    # DESeq2-style pseudocount smoothing). A raw ratio blows up whenever the
    # baseline is near zero — which happens constantly for packages whose
    # installs_90d/365d are barely bigger than installs_30d — producing numbers
    # like 200x-300x that are indistinguishable noise once anything gets capped.
    # Adding a fixed count to both sides damps that noise in proportion to how
    # small the counts are, while barely touching packages with real volume
    # (tens of thousands of installs/month).
    _TREND_PSEUDOCOUNT = 30.0

    # `alpha` above scales up (not a hard cutoff) when a package has little
    # installs recorded before its most recent tracked window — up to
    # `_TREND_MATURITY_BOOST`x at zero pre-window history, tapering linearly to
    # 1x (no boost) once that history passes `_TREND_MATURITY_THRESHOLD`. This
    # is what keeps recently-added-to-tracking packages (near-zero installs
    # before the last ~90 days) from reading as a real adoption spike — see
    # brewq-253 (bun ~250x on 98 pre-90d installs) — without collapsing them to
    # a flat neutral 1.0x the way a hard age cutoff would.
    _TREND_MATURITY_BOOST = 2.0
    _TREND_MATURITY_THRESHOLD = 1500.0

    @property
    def trending(self) -> float | None:
        """Growth signal: a recent installation rate as a multiple of this package's
        own span-weighted historical rate, e.g. 4.1 == "4.1x its own historical
        rate", 1.0 == unchanged, 0.5 == half its usual rate. None when there isn't
        enough analytics data to measure a baseline at all.

        The "recent" rate is anchored on the 90d window rather than the raw 30d
        count, i.e. installs_90d spread evenly over ~3 installs_30d-sized periods
        ("several weeks" each). That smooths out installs that are concentrated
        entirely in the most recent 30 days -- whether from a package that's new
        to tracking or from an established package whose rate only picked up
        recently -- instead of reading either case as a full-strength spike.
        """
        if self.installs_30d < 0:
            return None

        if self.installs_90d >= 0 and self.installs_365d >= 0:
            recent_rate = self.installs_90d / 3.0
            pre_window = max(0.0, self.installs_365d - self.installs_90d)
            baseline_rate = pre_window / 275.0 * 30.0
        elif self.installs_90d >= 0:
            # No 365d window to establish a pre-90d baseline at all: treat as
            # unproven (maximum maturity penalty below), using the 30d/90d gap
            # as a weak secondary rate signal.
            recent_rate = float(self.installs_30d)
            pre_window = 0.0
            baseline_rate = max(0.0, self.installs_90d - self.installs_30d) / 60.0 * 30.0
        elif self.installs_365d >= 0:
            recent_rate = float(self.installs_30d)
            pre_window = max(0.0, self.installs_365d - self.installs_30d)
            baseline_rate = pre_window / 335.0 * 30.0
        else:
            return None  # no older window to compare the recent rate against

        threshold = self._TREND_MATURITY_THRESHOLD
        penalty = max(0.0, (threshold - pre_window) / threshold)
        alpha = self._TREND_PSEUDOCOUNT * (1 + self._TREND_MATURITY_BOOST * penalty)
        return (recent_rate + alpha) / (baseline_rate + alpha)


def _cask_binaries(raw: dict) -> list[str]:
    result = []
    for artifact in raw.get("artifacts", []):
        if not isinstance(artifact, dict) or "binary" not in artifact:
            continue
        entry = artifact["binary"]
        if not isinstance(entry, list) or not entry:
            continue
        src = entry[0]
        if not isinstance(src, str):
            continue
        target = entry[1] if len(entry) > 1 and isinstance(entry[1], dict) else {}
        result.append(str(target.get("target", src.split("/")[-1])))
    return result


def from_formula(
    raw: dict,
    installs_30d: int = -1,
    installs_90d: int = -1,
    installs_365d: int = -1,
) -> Package:
    installed_list = raw.get("installed") or []
    installed_version = ""
    if installed_list:
        installed_version = installed_list[0].get("version", "")
    versions = raw.get("versions") or {}
    version = versions.get("stable", "")

    name = raw.get("full_name") or raw["name"]
    is_installed = bool(installed_list)
    return Package(
        name=name,
        type="formula",
        description=raw.get("desc") or "",
        url=raw.get("homepage") or "",
        version=version,
        installs_30d=installs_30d,
        installs_90d=installs_90d,
        installs_365d=installs_365d,
        installed=is_installed,
        deprecated=bool(raw.get("deprecated")),
        disabled=bool(raw.get("disabled")),
        aliases=list(raw.get("aliases") or []),
        installed_version=installed_version,
    )


def from_cask(
    raw: dict,
    installs_30d: int = -1,
    installs_90d: int = -1,
    installs_365d: int = -1,
) -> Package:
    installed_version = raw.get("installed") or ""
    if not isinstance(installed_version, str):
        installed_version = ""
    return Package(
        name=raw["token"],
        type="cask",
        description=raw.get("desc") or "",
        url=raw.get("homepage") or "",
        version=raw.get("version") or "",
        installs_30d=installs_30d,
        installs_90d=installs_90d,
        installs_365d=installs_365d,
        installed=bool(raw.get("installed")),
        deprecated=bool(raw.get("deprecated")),
        disabled=bool(raw.get("disabled")),
        binaries=_cask_binaries(raw),
        installed_version=installed_version,
    )
