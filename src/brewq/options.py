from __future__ import annotations

from dataclasses import dataclass, field
from difflib import get_close_matches
from typing import Any

from brewq.model import Package


@dataclass
class SearchOptions:
    query: list[str] = field(default_factory=list)
    pkg_type: str = "all"       # "formula" | "cask" | "all"
    sort: str = "popularity"    # "popularity" | "name"
    metric: str = "installs-30d"
    search_scope: str = "name"  # "name" | "all"
    columns_spec: str = "default"
    limit: int = 0
    json_output: bool = False

    @property
    def include_desc(self) -> bool:
        return self.search_scope != "name"


@dataclass
class ListOptions:
    pkg_type: str = "all"
    with_analytics: bool = False
    fetch_analytics: bool = False
    columns_spec: str = "default"
    limit: int = 0
    json_output: bool = False


def build_search_options(args: Any, cfg: dict) -> SearchOptions:
    metric = "installs-365d" if getattr(args, "year", False) else cfg["search"]["metric"]
    sort = "name" if getattr(args, "name", False) else cfg["search"]["sort"]
    # --top N implies popularity sort and sets the limit
    top = getattr(args, "top", None)
    limit = top or getattr(args, "limit", None) or cfg["output"]["limit"]
    if top:
        sort = "popularity"
    search_scope = "all" if getattr(args, "desc", False) else "name"
    return SearchOptions(
        query=list(args.query) if args.query else [],
        pkg_type=getattr(args, "type", cfg["search"]["type"]) or cfg["search"]["type"],
        sort=sort,
        metric=metric,
        search_scope=search_scope,
        columns_spec=getattr(args, "columns", None) or "default",
        limit=limit,
        json_output=getattr(args, "json", False),
    )


def build_list_options(args: Any, cfg: dict) -> ListOptions:
    return ListOptions(
        pkg_type=getattr(args, "type", "all") or "all",
        with_analytics=getattr(args, "analytics", False),
        fetch_analytics=getattr(args, "fetch", False),
        columns_spec=getattr(args, "columns", None) or "default",
        limit=getattr(args, "limit", None) or cfg["output"]["limit"],
        json_output=getattr(args, "json", False),
    )


def _simplify(text: str) -> str:
    """Match Homebrew search's lowkey normalization for name search."""
    return "".join(ch for ch in text.lower() if ch.isalnum() or ch in "@+")


def _name_fields(pkg: Package) -> list[str]:
    if pkg.type == "formula":
        return [pkg.name, *pkg.aliases]
    return [pkg.name]


def _matches(pkg: Package, query_terms: list[str], search_scope: str) -> bool:
    """Return True if all query terms match this package (case-insensitive)."""
    if not query_terms:
        return True
    if search_scope == "name":
        fields = [_simplify(field) for field in _name_fields(pkg)]
        return all(
            any(_simplify(term) in field for field in fields)
            for term in query_terms
        )
    else:
        search_text = pkg.name.lower()
        if pkg.description:
            search_text += " " + pkg.description.lower()
    return all(term in search_text for term in query_terms)


def _formula_fuzzy_names(packages: list[Package], query_terms: list[str], search_scope: str) -> set[str]:
    if search_scope != "name" or not query_terms:
        return set()
    query = _simplify(" ".join(query_terms))
    if not query:
        return set()

    by_simplified = {
        _simplify(pkg.name): pkg.name
        for pkg in packages
        if pkg.type == "formula"
    }
    close = get_close_matches(query, list(by_simplified), n=3, cutoff=0.75)
    return {by_simplified[name] for name in close if name != query}


def _match_score(pkg: Package, query_terms: list[str]) -> int:
    """Higher score = better name/token match."""
    if not query_terms:
        return 1
    name = _simplify(pkg.name)
    query = _simplify(" ".join(query_terms))
    # Exact token match
    if name == query:
        return 3
    # Name contains all terms
    if all(_simplify(t) in name for t in query_terms):
        return 2
    return 0


def rank(
    packages: list[Package],
    opts: SearchOptions,
) -> list[Package]:
    query_terms = [t.lower() for t in opts.query]

    # Filter by type
    if opts.pkg_type != "all":
        packages = [p for p in packages if p.type == opts.pkg_type]

    # Filter by query. Homebrew's formula search includes fuzzy matches in addition
    # to normalized substring matches; cask search remains token substring-only.
    formula_fuzzy_names = _formula_fuzzy_names(packages, query_terms, opts.search_scope)
    packages = [
        p for p in packages
        if _matches(p, query_terms, opts.search_scope) or p.name in formula_fuzzy_names
    ]

    # Filter out disabled/deprecated from top results (show them last)
    normal = [p for p in packages if not p.disabled and not p.deprecated]
    degraded = [p for p in packages if p.disabled or p.deprecated]

    if opts.sort == "name":
        normal.sort(key=lambda p: p.name.lower())
        degraded.sort(key=lambda p: p.name.lower())
    else:
        installs_key = (
            (lambda p: p.installs_365d)
            if opts.metric == "installs-365d"
            else (lambda p: p.installs_30d)
        )

        def sort_key(p: Package) -> tuple[int, int, str]:
            installs = max(installs_key(p), -1)
            return (-installs, -_match_score(p, query_terms), p.name.lower())

        normal.sort(key=sort_key)
        degraded.sort(key=sort_key)

    result = normal + degraded

    if opts.limit > 0:
        result = result[: opts.limit]

    return result


def rank_installed(packages: list[Package], opts: ListOptions) -> list[Package]:
    if opts.pkg_type != "all":
        packages = [p for p in packages if p.type == opts.pkg_type]
    packages.sort(key=lambda p: (p.type, p.name.lower()))
    if opts.limit > 0:
        packages = packages[: opts.limit]
    return packages
