from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from brewq.model import Package


@dataclass
class SearchOptions:
    query: list[str] = field(default_factory=list)
    pkg_type: str = "all"       # "formula" | "cask" | "all"
    sort: str = "popularity"    # "popularity" | "name"
    metric: str = "installs-30d"
    include_desc: bool = True   # name+description by default (canonical spec)
    columns_spec: str = "default"
    limit: int = 0
    json_output: bool = False


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
    return SearchOptions(
        query=list(args.query) if args.query else [],
        pkg_type=getattr(args, "type", cfg["search"]["type"]) or cfg["search"]["type"],
        sort=sort,
        metric=metric,
        # --name-only disables description search; --desc is a compat no-op
        include_desc=not getattr(args, "name_only", False),
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


def _matches(pkg: Package, query_terms: list[str], include_desc: bool) -> bool:
    """Return True if all query terms match this package (case-insensitive)."""
    if not query_terms:
        return True
    search_text = pkg.name.lower()
    if include_desc and pkg.description:
        search_text += " " + pkg.description.lower()
    return all(term in search_text for term in query_terms)


def _match_score(pkg: Package, query_terms: list[str]) -> int:
    """Higher score = better name/token match. 0 = description-only match."""
    if not query_terms:
        return 1
    name = pkg.name.lower()
    # Exact token match
    if name == " ".join(query_terms):
        return 3
    # Name contains all terms
    if all(t in name for t in query_terms):
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

    # Filter by query
    packages = [p for p in packages if _matches(p, query_terms, opts.include_desc)]

    # Filter out disabled/deprecated from top results (show them last)
    normal = [p for p in packages if not p.disabled and not p.deprecated]
    degraded = [p for p in packages if p.disabled or p.deprecated]

    if opts.sort == "name":
        normal.sort(key=lambda p: p.name.lower())
        degraded.sort(key=lambda p: p.name.lower())
    else:
        # popularity sort: primary = match_score, secondary = install count
        installs_key = (lambda p: p.installs_365d) if opts.metric == "installs-365d" else (lambda p: p.installs_30d)

        def sort_key(p: Package) -> tuple[int, int]:
            return (_match_score(p, query_terms), installs_key(p))

        normal.sort(key=sort_key, reverse=True)
        degraded.sort(key=sort_key, reverse=True)

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
