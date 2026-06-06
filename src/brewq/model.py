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
    installs_30d: int  # -1 = unknown
    installs_365d: int  # -1 = unknown
    installed: bool
    deprecated: bool
    disabled: bool
    aliases: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.disabled:
            return "disabled"
        if self.deprecated:
            return "deprecated"
        return ""

    @property
    def installs(self) -> int:
        """Default popularity metric (30-day)."""
        return self.installs_30d


def from_formula(raw: dict, installs_30d: int = -1, installs_365d: int = -1) -> Package:
    installed_list = raw.get("installed") or []
    version = ""
    if installed_list:
        version = installed_list[0].get("version", "")
    if not version:
        versions = raw.get("versions") or {}
        version = versions.get("stable", "")

    return Package(
        name=raw.get("full_name") or raw["name"],
        type="formula",
        description=raw.get("desc") or "",
        url=raw.get("homepage") or "",
        version=version,
        installs_30d=installs_30d,
        installs_365d=installs_365d,
        installed=bool(installed_list),
        deprecated=bool(raw.get("deprecated")),
        disabled=bool(raw.get("disabled")),
        aliases=list(raw.get("aliases") or []),
    )


def from_cask(raw: dict, installs_30d: int = -1, installs_365d: int = -1) -> Package:
    name_field = raw.get("name") or []
    display_name = name_field[0] if isinstance(name_field, list) and name_field else raw["token"]

    return Package(
        name=raw["token"],
        type="cask",
        description=raw.get("desc") or "",
        url=raw.get("homepage") or "",
        version=raw.get("version") or "",
        installs_30d=installs_30d,
        installs_365d=installs_365d,
        installed=bool(raw.get("installed")),
        deprecated=bool(raw.get("deprecated")),
        disabled=bool(raw.get("disabled")),
        aliases=[display_name] if display_name != raw["token"] else [],
    )
