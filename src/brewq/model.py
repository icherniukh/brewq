from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
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
    # (tens of thousands of installs/month). Calibrated against the live seed
    # cache: at alpha=20, single/double-digit-install packages get pulled down
    # to single-digit multipliers instead of pegging a hard ceiling, while
    # household-name tools (jq, git, ripgrep) land within ~50% of neutral.
    _TREND_PSEUDOCOUNT = 20.0

    @property
    def trending(self) -> float | None:
        """Growth signal: the most recent monthly install rate as a multiple of this
        package's own span-weighted historical monthly rate, e.g. 4.1 == "4.1x its
        own historical rate", 1.0 == unchanged, 0.5 == half its usual rate. None
        when there isn't enough analytics data to measure a baseline at all.
        """
        if self.installs_30d < 0:
            return None
        recent_rate = float(self.installs_30d)

        history_total = 0.0
        history_days = 0.0
        if self.installs_90d >= 0:
            history_total += max(0.0, self.installs_90d - self.installs_30d)
            history_days += 60.0
            if self.installs_365d >= 0:
                history_total += max(0.0, self.installs_365d - self.installs_90d)
                history_days += 275.0
        elif self.installs_365d >= 0:
            history_total += max(0.0, self.installs_365d - self.installs_30d)
            history_days += 335.0

        if history_days == 0:
            return None  # no older window to compare the recent rate against

        baseline_rate = history_total / history_days * 30.0
        alpha = self._TREND_PSEUDOCOUNT
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
    version = ""
    if installed_list:
        version = installed_list[0].get("version", "")
    if not version:
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
    )


def from_cask(
    raw: dict,
    installs_30d: int = -1,
    installs_90d: int = -1,
    installs_365d: int = -1,
) -> Package:
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
    )
