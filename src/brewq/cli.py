from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Sequence

from brewq import cache as cache_mod
from brewq import columns as columns_mod
from brewq import config as config_mod
from brewq import options as options_mod
from brewq import render as render_mod

_COMMANDS = frozenset({"list", "cache", "config", "random"})
_BREW_INFO_BATCH_SIZE = 100
_FORMATTER = argparse.RawDescriptionHelpFormatter

_SEARCH_EPILOG = """\
Examples:
  brewq ripgrep
  brewq -t 10 json
  brewq -s 365d rust
  brewq terminal multiplexer

Commands: list  cache  config
"""

_LIST_EPILOG = """\
Examples:
  brewq list
  brewq list --fetch
  brewq list -p full
  brewq list -c name,type,version
"""

_CACHE_EPILOG = """\
Examples:
  brewq cache status
  brewq cache refresh
  brewq cache refresh --force
  brewq cache clear

Use `brewq config path` to find the config file.
"""

_CONFIG_EPILOG = """\
Examples:
  brewq config path

The config file controls default columns and cache freshness.
"""


def _build_search_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="brewq",
        description="Query Homebrew packages with cached analytics.",
        epilog=_SEARCH_EPILOG,
        formatter_class=_FORMATTER,
    )
    parser.add_argument("query", nargs="*", help="Search terms")
    parser.add_argument("-s", "--sort", metavar="FIELD",
                        help="Sort by: 30d (i30), 365d (i365), name  [default: 30d]")
    parser.add_argument("-l", "--installed", action="store_true",
                        help="Filter to installed packages")
    parser.add_argument("-p", "--preset", metavar="NAME",
                        help="Column preset: compact, full")
    parser.add_argument("-c", "--columns", metavar="KEYS",
                        help="Columns: name (n), 30d, 90d, 365d, pop, bin, type (t), version (v), desc (d), inst (i), status, url (h)")
    parser.add_argument("-t", "--top", type=int, metavar="N",
                        help="Show top N by installs")
    parser.add_argument("--tsv", action="store_true",
                        help="Tab-separated output for scripting")
    return parser


def _build_command_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="brewq", formatter_class=_FORMATTER)
    subparsers = parser.add_subparsers(dest="command")

    # list
    lst = subparsers.add_parser(
        "list",
        help="Show installed formulae and casks",
        description="Show installed formulae and casks with the same column system as search.",
        epilog=_LIST_EPILOG,
        formatter_class=_FORMATTER,
    )
    lst.add_argument("--analytics", action="store_true",
                     help="Include analytics columns (cache-backed)")
    lst.add_argument("--fetch", action="store_true",
                     help="Fetch missing per-package analytics (implies --analytics)")
    lst.add_argument("-p", "--preset", metavar="NAME",
                     help="Column preset: compact, full")
    lst.add_argument("-c", "--columns", metavar="KEYS",
                     help="Explicit columns: comma-joined keys")
    lst.add_argument("--limit", type=int, metavar="N")
    lst.add_argument("--tsv", action="store_true",
                     help="Output raw tab-separated rows for shell scripting")

    # cache
    cache = subparsers.add_parser(
        "cache",
        help="Inspect and manage the local cache",
        description="Inspect cache status and refresh behavior.",
        epilog=_CACHE_EPILOG,
        formatter_class=_FORMATTER,
    )
    cache_sub = cache.add_subparsers(dest="cache_command", required=True)
    cache_sub.add_parser("status", help="Show cache path, age, counts, and lock state")
    refresh_p = cache_sub.add_parser("refresh", help="Refresh local cache data")
    refresh_p.add_argument("--force", action="store_true",
                           help="Refresh even when cache is fresh")
    cache_sub.add_parser("clear", help="Remove local cache files")

    # config
    config_p = subparsers.add_parser(
        "config",
        help="Show configuration info",
        description="Show where brewq reads configuration.",
        epilog=_CONFIG_EPILOG,
        formatter_class=_FORMATTER,
    )
    config_p.add_argument("config_sub_cmd", nargs="?", choices=["path"], default="path")

    # random
    rand_p = subparsers.add_parser(
        "random",
        help="Run a random layout lab search",
        description="Pick a random query and output layout, then run the normal search path.",
        formatter_class=_FORMATTER,
    )
    rand_p.add_argument("--seed", type=int, metavar="N",
                        help="Fix the random seed for a reproducible lab run")

    return parser


def _normalize_argv(argv: list[str]) -> list[str]:
    if argv and argv[0] == "update-cache":
        return ["cache", "refresh", *argv[1:]]
    return argv


def _validate_column_flags(args: argparse.Namespace) -> str | None:
    """Return an error string if -p and -c are both set, else None."""
    if getattr(args, "preset", None) and getattr(args, "columns", None):
        return "cannot use both -p/--preset and -c/--columns"
    return None


def _cmd_list(args: argparse.Namespace, cfg: dict) -> int:
    err = _validate_column_flags(args)
    if err:
        print(f"brewq: {err}", file=sys.stderr)
        return 1

    opts = options_mod.build_list_options(args, cfg)
    list_cols_cfg = cfg["list"]["columns"]

    try:
        col_defs = columns_mod.resolve(
            opts.columns_spec,
            list_cols_cfg,
            profiles=columns_mod.list_profiles(),
        )
    except ValueError as exc:
        print(f"brewq: {exc}", file=sys.stderr)
        return 1

    if opts.with_analytics or opts.fetch_analytics:
        col_defs = _ensure_list_analytics_column(col_defs)

    try:
        from brewq import brew as brew_mod
        raw = brew_mod.info_installed()
    except FileNotFoundError as exc:
        print(f"brewq: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"brewq: failed to query installed packages: {exc}", file=sys.stderr)
        return 1

    from brewq.model import from_cask, from_formula
    packages = []
    for f in raw.get("formulae", []):
        packages.append(from_formula(f))
    for c in raw.get("casks", []):
        packages.append(from_cask(c))

    if opts.fetch_analytics:
        try:
            print("Fetching analytics…", file=sys.stderr)
            cache_mod.refresh(force=False)
        except Exception as exc:
            print(f"brewq: analytics fetch failed: {exc}", file=sys.stderr)
        _merge_cached_analytics(packages)
    elif opts.with_analytics:
        _merge_cached_analytics(packages)

    packages = options_mod.rank_installed(packages, opts)

    if opts.tsv_output:
        render_mod.render_tsv(packages, col_defs, out=sys.stdout)
    else:
        render_mod.render_table(packages, col_defs, out=sys.stdout)
    return 0


def _merge_cached_analytics(packages: list) -> None:
    try:
        cached = cache_mod.load_packages()
    except Exception:
        return
    by_name = {p.name: p for p in cached}
    for pkg in packages:
        cached_pkg = by_name.get(pkg.name)
        if cached_pkg:
            pkg.installs_30d = cached_pkg.installs_30d
            pkg.installs_90d = cached_pkg.installs_90d
            pkg.installs_365d = cached_pkg.installs_365d


def _ensure_list_analytics_column(col_defs: list) -> list:
    keys = {c.key for c in col_defs}
    if keys & {"installs_30d", "installs_90d", "installs_365d"}:
        return col_defs
    installs_col = columns_mod.resolve("installs_30d", [])[0]
    desc_idx = next((i for i, col in enumerate(col_defs) if col.key == "description"), None)
    if desc_idx is None:
        return [*col_defs, installs_col]
    return [*col_defs[:desc_idx], installs_col, *col_defs[desc_idx:]]


def _cmd_cache(args: argparse.Namespace, cfg: dict) -> int:
    sub = args.cache_command

    if sub == "status":
        s = cache_mod.status()
        age = s["age_seconds"]
        age_str = f"{age}s" if age is not None else "n/a"
        max_age = cfg["cache"]["max_age_seconds"]
        print(f"path:      {s['path']}")
        print(f"exists:    {s['exists']}")
        print(f"age:       {age_str}")
        print(f"max age:   {max_age}s")
        print(f"formulae:  {s['formula_count']}")
        print(f"casks:     {s['cask_count']}")
        print(f"analytics: {s['has_analytics']}")
        print(f"locked:    {s['locked']}")
        return 0

    if sub == "refresh":
        force = getattr(args, "force", False)
        print("Refreshing cache…", file=sys.stderr)
        try:
            cache_mod.refresh(force=force)
            s = cache_mod.status()
            print(
                f"Done. {s['formula_count']} formulae, {s['cask_count']} casks.",
                file=sys.stderr,
            )
        except Exception as exc:
            print(f"brewq: cache refresh failed: {exc}", file=sys.stderr)
            return 1
        return 0

    if sub == "clear":
        cache_mod.clear()
        print("Cache cleared.", file=sys.stderr)
        return 0

    return 1


def _cmd_config(args: argparse.Namespace) -> int:
    print(config_mod.config_path())
    return 0


_RANDOM_TERMS = (
    "json", "http", "markdown", "terminal", "pdf", "video",
    "image", "database", "git", "compress", "encrypt", "monitor",
    "search", "diff", "sync", "backup", "proxy", "log", "parser",
    "fuzzy", "render", "stream", "lint", "format", "test",
)
_RANDOM_SORTS = ("30d", "30d", "365d", "90d", "name")
_RANDOM_LAYOUTS = (
    ("default", None, None),
    ("compact", "compact", None),
    ("full", "full", None),
    ("metrics", None, "name,30d,90d,365d,description"),
    ("ops", None, "name,type,version,bin,description"),
    ("links", None, "name,30d,url"),
)


def _cmd_random(args: argparse.Namespace, cfg: dict) -> int:
    import random as random_mod

    rng = random_mod.Random(getattr(args, "seed", None))
    query = rng.choice(_RANDOM_TERMS)
    sort = rng.choice(_RANDOM_SORTS)
    top = rng.randint(4, 10)
    _, preset, columns = rng.choice(_RANDOM_LAYOUTS)

    command = ["brewq", "-t", str(top), "-s", sort]
    if preset:
        command.extend(["-p", preset])
    if columns:
        command.extend(["-c", columns])
    command.append(query)
    print(" ".join(command), file=sys.stderr)

    search_args = argparse.Namespace(
        query=[query],
        sort=sort,
        installed=False,
        preset=preset,
        columns=columns,
        top=top,
        tsv=False,
    )
    return _cmd_search(search_args, cfg)


def _cmd_search(args: argparse.Namespace, cfg: dict) -> int:
    err = _validate_column_flags(args)
    if err:
        print(f"brewq: {err}", file=sys.stderr)
        return 1

    try:
        opts = options_mod.build_search_options(args, cfg)
    except ValueError as exc:
        print(f"brewq: {exc}", file=sys.stderr)
        return 1

    if not opts.query and not opts.installed_only:
        _build_search_parser().print_help()
        return 2

    default_cols = cfg["output"]["columns"]
    try:
        col_defs = columns_mod.resolve(opts.columns_spec, default_cols)
    except ValueError as exc:
        print(f"brewq: {exc}", file=sys.stderr)
        return 1

    packages = cache_mod.load_packages()

    if not packages:
        print(
            "Cache not built yet. Building in background; showing live results (slower)…",
            file=sys.stderr,
        )
        try:
            cache_mod.refresh_background()
        except Exception:
            pass
        packages = _live_search(opts)
    else:
        cache_mod.refresh_background()
        packages = _augment_with_live_search(packages, opts)

    ranked = options_mod.rank(packages, opts)

    if not ranked:
        query_str = " ".join(opts.query) if opts.query else "(installed filter)"
        print(f"No results for: {query_str}", file=sys.stderr)
        return 0

    if opts.tsv_output:
        render_mod.render_tsv(ranked, col_defs, out=sys.stdout)
    else:
        render_mod.render_table(ranked, col_defs, out=sys.stdout, sorted_col=opts.sort)
    return 0


def _brew_search_names(opts: options_mod.SearchOptions) -> list[str]:
    brew = shutil.which("brew")
    if not brew:
        return []
    command = [brew, "search", "--", *opts.query]
    result = subprocess.run(command, capture_output=True, text=True)
    return [
        line.split(":", 1)[0].strip()
        for line in result.stdout.splitlines()
        if line.strip() and not line.startswith(("==>", "Warning:"))
    ]


def _packages_for_names(names: list[str]) -> list:
    if not names:
        return []
    from brewq import brew as brew_mod
    from brewq.model import from_cask, from_formula

    packages = []
    for start in range(0, len(names), _BREW_INFO_BATCH_SIZE):
        raw = brew_mod.info_packages(names[start:start + _BREW_INFO_BATCH_SIZE])
        for f in raw.get("formulae", []):
            packages.append(from_formula(f))
        for c in raw.get("casks", []):
            packages.append(from_cask(c))
    return packages


def _augment_with_live_search(packages: list, opts: options_mod.SearchOptions) -> list:
    if not opts.query:
        return packages
    try:
        names = _brew_search_names(opts)
        known = {pkg.name for pkg in packages}
        missing = [name for name in names if name not in known]
        return [*packages, *_packages_for_names(missing)]
    except Exception:
        return packages


def _live_search(opts: options_mod.SearchOptions) -> list:
    if not opts.query:
        return []
    try:
        return _packages_for_names(_brew_search_names(opts))
    except Exception:
        return []


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    raw_argv = _normalize_argv(raw_argv)

    cfg = config_mod.load()

    # Route subcommands only when they are the first token. Search remains the
    # default command even when query terms are named like subcommands.
    if raw_argv and raw_argv[0] in _COMMANDS:
        args = _build_command_parser().parse_args(raw_argv)
        if args.command == "list":
            return _cmd_list(args, cfg)
        if args.command == "cache":
            return _cmd_cache(args, cfg)
        if args.command == "config":
            return _cmd_config(args)
        if args.command == "random":
            return _cmd_random(args, cfg)

    args = _build_search_parser().parse_args(raw_argv)
    return _cmd_search(args, cfg)


if __name__ == "__main__":
    raise SystemExit(main())
