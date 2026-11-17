from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

from brewq import spell
from brewq.model import Package

SORT_CHOICES = ("90d", "30d", "365d", "trend", "name")
# Migration diagnostics only; public sort input is exact.
_REMOVED_SORTS = {
    "installs_90d": "90d", "90": "90d", "i90": "90d", "default": "90d",
    "installs_30d": "30d", "installs": "30d", "install": "30d", "30": "30d", "i30": "30d",
    "installs_365d": "365d", "365": "365d", "i365": "365d", "year": "365d",
    "y": "365d", "annual": "365d", "trending": "trend", "hot": "trend",
    "n": "name", "nm": "name", "alpha": "name", "alphabetical": "name", "az": "name", "a-z": "name",
}


def sort_choices_text() -> str:
    return ", ".join(SORT_CHOICES)


def parse_sort(raw: str) -> str:
    """Validate the exact public sort field."""
    replacement = _REMOVED_SORTS.get(raw.strip().lower())
    if replacement:
        raise ValueError(f"Sort field {raw!r} was removed; use {replacement!r}")
    if raw not in SORT_CHOICES:
        raise ValueError(f"Unknown sort field {raw!r}.{spell.suggestion(raw, SORT_CHOICES)} "
                         f"Valid: {sort_choices_text()}")
    return raw


@dataclass
class SearchOptions:
    query: list[str] = field(default_factory=list)
    sort: str = "90d"
    columns_spec: str | list = "default"
    limit: int = 0
    tsv_output: bool = False
    installed_only: bool = False
    show_all: bool = False
    reverse: bool = False
    regex: re.Pattern[str] | None = None
    # Matches before a positive view limit is applied; used for honest counts.
    eligible_total: int = 0


def resolve_reverse(explicit: bool | None, cfg: dict) -> bool:
    """Resolve reverse order. BREWQ_NO_REVERSE=1 is the immediate kill switch."""
    if os.environ.get("BREWQ_NO_REVERSE", "").strip().lower() in {"1", "true", "yes", "on"}:
        return False
    if explicit is not None:
        return explicit
    return bool(cfg.get("search", {}).get("reverse", False))


def build_search_options(args: Any, cfg: dict) -> SearchOptions:
    raw_sort = getattr(args, "sort", None)
    top = getattr(args, "top", None)

    if raw_sort is not None:
        sort = parse_sort(raw_sort)  # raises ValueError on unknown input
    else:
        cfg_sort = cfg["search"].get("sort", "90d")
        sort = parse_sort(cfg_sort)

    # Terminal height sizes the layout, never the result set: a small window
    # must not silently discard matches.
    cfg_limit = cfg["output"]["limit"]
    limit = top or cfg_limit

    columns_spec = getattr(args, "columns", None)
    if columns_spec is None:
        columns_spec = "default"

    query = list(args.query) if args.query else []
    return SearchOptions(
        query=query,
        regex=_query_regex(query),
        sort=sort,
        columns_spec=columns_spec,
        limit=limit,
        tsv_output=getattr(args, "tsv", False),
        installed_only=getattr(args, "installed", False),
        show_all=getattr(args, "all", False),
        reverse=resolve_reverse(getattr(args, "reverse", None), cfg),
    )


_STRIP = str.maketrans("", "", "".join(
    ch for ch in map(chr, range(128)) if not (ch.isalnum() or ch in "@+")
))


def _simplify(text: str) -> str:
    """Match Homebrew search's lowkey normalization for name search."""
    return text.lower().translate(_STRIP)


def _name_fields(pkg: Package) -> list[str]:
    if pkg.type == "formula":
        return [pkg.name, *pkg.aliases]
    return [pkg.name]


def _matcher(query_terms: list[str], regex: re.Pattern[str] | None):
    """Build a predicate: all query terms match a package's name, alias, or description."""
    if regex is not None:
        def regex_match(pkg: Package) -> bool:
            return any(regex.search(f) for f in (*_name_fields(pkg), pkg.description or ""))
        return regex_match
    if not query_terms:
        return lambda pkg: True

    terms = [t.lower() for t in query_terms]
    simple_terms = [_simplify(t) for t in terms]
    pairs = list(zip(terms, simple_terms, strict=True))
    simplify = _simplify

    def match(pkg: Package) -> bool:
        name = pkg.name.lower()
        aliases = pkg.aliases if pkg.type == "formula" else ()
        desc = pkg.description.lower() if pkg.description else ""
        simple_names: list[str] | None = None
        for term, simple in pairs:
            if term in name or (desc and term in desc):
                continue
            if aliases and any(term in a.lower() for a in aliases):
                continue
            if simple_names is None:
                simple_names = [simplify(name), *(simplify(a) for a in aliases)]
            if not any(simple in field for field in simple_names):
                return False
        return True

    return match


def _query_regex(query: list[str]) -> re.Pattern[str] | None:
    """Compile a `/pattern/` query the way `brew search` does."""
    joined = " ".join(query)
    if len(joined) < 3 or not (joined.startswith("/") and joined.endswith("/")):
        return None
    try:
        return re.compile(joined[1:-1])
    except re.error as exc:
        raise ValueError(f"{joined} is not a valid regex ({exc})") from exc


def _spell_names(packages: list[Package], query_terms: list[str]) -> set[tuple[str, str]]:
    """(type, name) pairs `brew search` adds via DidYouMean spell correction."""
    if not query_terms:
        return set()
    query = " ".join(query_terms)
    found: set[tuple[str, str]] = set()
    for kind in ("formula", "cask"):
        names = [p.name for p in packages if p.type == kind]
        found.update((kind, name) for name in spell.correct(query, names))
    return found


def _match_score(pkg: Package, query_terms: list[str]) -> int:
    """Higher score = better name/token match."""
    if not query_terms:
        return 1
    name = _simplify(pkg.name)
    query = _simplify(" ".join(query_terms))
    if name == query:
        return 3
    if all(_simplify(t) in name for t in query_terms):
        return 2
    return 0


def _exact_match_score(pkg: Package, query_terms: list[str]) -> int:
    if not query_terms:
        return 0
    query = _simplify(" ".join(query_terms))
    if not query:
        return 0
    return 1 if any(_simplify(field) == query for field in _name_fields(pkg)) else 0


def rank(
    packages: list[Package],
    opts: SearchOptions,
) -> list[Package]:
    query_terms = [t.lower() for t in opts.query]

    # Filter to installed packages when requested
    if opts.installed_only:
        packages = [p for p in packages if p.installed]

    spelled = _spell_names(packages, query_terms) if opts.regex is None else set()
    matches = _matcher(query_terms, opts.regex)
    packages = [p for p in packages if matches(p) or (p.type, p.name) in spelled]
    # Hide deprecated/disabled only when a view limit exists and results would
    # overflow it. No view limit (piped/non-TTY) means no constraint.
    if not opts.show_all and 0 < opts.limit < len(packages):
        packages = [p for p in packages if not p.deprecated and not p.disabled]

    # Push disabled/deprecated to the end
    normal = [p for p in packages if not p.disabled and not p.deprecated]
    degraded = [p for p in packages if p.disabled or p.deprecated]

    if opts.sort == "name":
        normal.sort(key=lambda p: p.name.lower())
        degraded.sort(key=lambda p: p.name.lower())
    else:
        def metric_key(p: Package) -> float:
            if opts.sort == "trend":
                return p.trending if p.trending is not None else float("-inf")
            if opts.sort == "365d":
                return max(p.installs_365d, -1)
            if opts.sort == "90d":
                return max(p.installs_90d, -1)
            return max(p.installs_30d, -1)

        def sort_key(p: Package) -> tuple[int, float, int, str]:
            return (
                -_exact_match_score(p, query_terms),
                -metric_key(p),
                -_match_score(p, query_terms),
                p.name.lower(),
            )

        normal.sort(key=sort_key)
        degraded.sort(key=sort_key)

    result = normal + degraded
    opts.eligible_total = len(result)
    if opts.limit > 0:
        result = result[: opts.limit]
    if opts.reverse:
        result.reverse()
    return result
