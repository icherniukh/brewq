from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path


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

    @property
    def popularity_score(self) -> int:
        """Composite 0-100 score: log-weighted install volume + trend momentum."""
        i30 = max(self.installs_30d, 0)
        i365 = max(self.installs_365d, 0)
        if i30 == 0 and i365 == 0:
            return -1
        if i365 > 0 and i30 > 0:
            annual = i30 * 12 * 0.6 + i365 * 0.4
        elif i30 > 0:
            annual = i30 * 12
        else:
            annual = i365
        base = min(100, int(math.log10(annual + 1) * 16.7))
        if i365 > 0 and i30 > 0:
            monthly_hist = i365 / 12
            if monthly_hist > 0:
                trend = i30 / monthly_hist
                if trend > 1.5:
                    base = min(100, int(base * 1.15))
                elif trend > 1.2:
                    base = min(100, int(base * 1.07))
                elif trend < 0.5:
                    base = max(0, int(base * 0.85))
                elif trend < 0.8:
                    base = max(0, int(base * 0.93))
        return base


def formula_binaries(name: str, installed: bool) -> list[str]:
    if not installed:
        return []
    simple = name.split("/")[-1]
    for prefix in ("/opt/homebrew/opt", "/usr/local/opt"):
        bin_dir = Path(f"{prefix}/{simple}/bin")
        if bin_dir.exists():
            try:
                return sorted(f.name for f in bin_dir.iterdir())
            except OSError:
                pass
    return []


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
        binaries=formula_binaries(name, is_installed),
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
