from __future__ import annotations

from dataclasses import dataclass, field
from difflib import get_close_matches
from typing import Any

from brewq.model import Package

# Sort aliases map user input to canonical sort fields.
_SORT_ALIASES: dict[str, str] = {
    # installs_30d
    "installs_30d": "installs_30d",
    "installs": "installs_30d",
    "install": "installs_30d",
    "30": "installs_30d",
    "30d": "installs_30d",
    "i30": "installs_30d",
    "default": "installs_30d",
    # installs_90d
    "installs_90d": "installs_90d",
    "90": "installs_90d",
    "90d": "installs_90d",
    "i90": "installs_90d",
    # installs_365d
    "installs_365d": "installs_365d",
    "365": "installs_365d",
    "365d": "installs_365d",
    "i365": "installs_365d",
    "year": "installs_365d",
    "y": "installs_365d",
    "annual": "installs_365d",
    # name
    "name": "name",
    "n": "name",
    "nm": "name",
    "alpha": "name",
    "alphabetical": "name",
    "az": "name",
    "a-z": "name",
}

def parse_sort(raw: str) -> str:
    """Resolve a sort alias to a canonical sort field."""
    normalized = raw.strip().lower()
    result = _SORT_ALIASES.get(normalized)
    if result is None:
        valid = "30d (i30, installs), 90d (i90), 365d (i365, y), name (n)"
        raise ValueError(f"Unknown sort field {raw!r}. Valid: {valid}")
    return result


@dataclass
class SearchOptions:
    query: list[str] = field(default_factory=list)
    sort: str = "installs_30d"
    columns_spec: str = "default"
    limit: int = 0
    tsv_output: bool = False
    installed_only: bool = False
    show_all: bool = False


@dataclass
class ListOptions:
    with_analytics: bool = False
    columns_spec: str = "default"
    limit: int = 0
    tsv_output: bool = False


def build_search_options(args: Any, cfg: dict, *, tty_rows: int | None = None) -> SearchOptions:
    raw_sort = getattr(args, "sort", None)
    top = getattr(args, "top", None)

    if raw_sort:
        sort = parse_sort(raw_sort)  # raises ValueError on unknown input
    elif top:
        sort = "installs_30d"  # --top implies popularity ranking
    else:
        cfg_sort = cfg["search"].get("sort", "installs_30d")
        sort = parse_sort(cfg_sort)

    cfg_limit = cfg["output"]["limit"]
    if top:
        limit = top
    elif cfg_limit > 0:
        limit = cfg_limit
    elif tty_rows is not None:
        limit = max(5, tty_rows - 6)
    else:
        limit = 0

    columns_spec = (
        getattr(args, "columns", None)
        or getattr(args, "preset", None)
        or "default"
    )

    return SearchOptions(
        query=list(args.query) if args.query else [],
        sort=sort,
        columns_spec=columns_spec,
        limit=limit,
        tsv_output=getattr(args, "tsv", False),
        installed_only=getattr(args, "installed", False),
        show_all=getattr(args, "all", False),
    )


def build_list_options(args: Any, cfg: dict) -> ListOptions:
    columns_spec = (
        getattr(args, "columns", None)
        or getattr(args, "preset", None)
        or "default"
    )
    return ListOptions(
        with_analytics=getattr(args, "analytics", False),
        columns_spec=columns_spec,
        limit=getattr(args, "limit", None) or 0,
        tsv_output=getattr(args, "tsv", False),
    )


def _simplify(text: str) -> str:
    """Match Homebrew search's lowkey normalization for name search."""
    return "".join(ch for ch in text.lower() if ch.isalnum() or ch in "@+")


def _name_fields(pkg: Package) -> list[str]:
    if pkg.type == "formula":
        return [pkg.name, *pkg.aliases]
    return [pkg.name]


def _matches(pkg: Package, query_terms: list[str]) -> bool:
    """Return True if all query terms match this package's name or description."""
    if not query_terms:
        return True
    search_text = " ".join(_name_fields(pkg)).lower()
    if pkg.description:
        search_text += " " + pkg.description.lower()
    simplified_fields = [_simplify(field) for field in _name_fields(pkg)]
    return all(
        term.lower() in search_text
        or any(_simplify(term) in field for field in simplified_fields)
        for term in query_terms
    )


def _formula_fuzzy_names(packages: list[Package], query_terms: list[str]) -> set[str]:
    if not query_terms:
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
    return {
        by_simplified[name]
        for name in close
        if name != query and _is_subsequence(name, query)
    }


def _is_subsequence(candidate: str, query: str) -> bool:
    """Allow Homebrew-like deletion matches without broad anagram-ish drift."""
    query_chars = iter(query)
    return all(ch in query_chars for ch in candidate)


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

    cached_fuzzy: set[str] | None = None
    if not opts.show_all:
        # Filter deprecated/disabled only when a view limit exists and results would overflow it.
        # No view limit (piped/non-TTY) means no constraint — include all.
        if opts.limit > 0:
            cached_fuzzy = _formula_fuzzy_names(packages, query_terms)
            _total = sum(1 for p in packages if _matches(p, query_terms) or p.name in cached_fuzzy)
            if _total > opts.limit:
                packages = [p for p in packages if not p.deprecated and not p.disabled]
                cached_fuzzy = None  # stale after filter; recompute below

    formula_fuzzy_names = cached_fuzzy if cached_fuzzy is not None else _formula_fuzzy_names(packages, query_terms)
    packages = [
        p for p in packages
        if _matches(p, query_terms) or p.name in formula_fuzzy_names
    ]

    # Push disabled/deprecated to the end
    normal = [p for p in packages if not p.disabled and not p.deprecated]
    degraded = [p for p in packages if p.disabled or p.deprecated]

    if opts.sort == "name":
        normal.sort(key=lambda p: p.name.lower())
        degraded.sort(key=lambda p: p.name.lower())
    else:
        installs_key = (
            (lambda p: p.installs_365d) if opts.sort == "installs_365d"
            else (lambda p: p.installs_90d) if opts.sort == "installs_90d"
            else (lambda p: p.installs_30d)
        )

        def sort_key(p: Package) -> tuple[int, int, int, str]:
            installs = max(installs_key(p), -1)
            return (
                -_exact_match_score(p, query_terms),
                -installs,
                -_match_score(p, query_terms),
                p.name.lower(),
            )

        normal.sort(key=sort_key)
        degraded.sort(key=sort_key)

    result = normal + degraded

    if opts.limit > 0:
        result = result[: opts.limit]

    return result


def rank_installed(packages: list[Package], opts: ListOptions) -> list[Package]:
    packages.sort(key=lambda p: (p.type, p.name.lower()))
    if opts.limit > 0:
        packages = packages[: opts.limit]
    return packages
