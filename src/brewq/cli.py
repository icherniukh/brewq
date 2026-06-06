from __future__ import annotations

import argparse
import subprocess
import shutil
import sys
from collections.abc import Sequence

from brewq import cache as cache_mod
from brewq import columns as columns_mod
from brewq import config as config_mod
from brewq import options as options_mod
from brewq import render as render_mod


_COMMANDS = frozenset({"list", "cache", "config"})


def _build_search_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="brewq",
        description="Rich Homebrew search with cached analytics.",
        epilog="Commands: list, cache, config",
    )
    parser.add_argument("query", nargs="*", help="Search terms")
    parser.add_argument("--type", choices=["formula", "cask", "all"], default=None,
                        help="Limit to formula, cask, or all (default: all)")
    parser.add_argument("--desc", action="store_true",
                        help="Also search package descriptions")
    parser.add_argument("-n", "--name", action="store_true",
                        help="Sort results by name instead of popularity")
    parser.add_argument("-y", "--year", action="store_true",
                        help="Show 365-day installs instead of 30-day")
    parser.add_argument("--columns", metavar="SPEC",
                        help="Column spec: profile name (compact/full) or comma-joined keys")
    parser.add_argument("--limit", type=int, metavar="N",
                        help="Cap results at N rows")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON instead of a table")
    return parser


def _build_command_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="brewq")
    subparsers = parser.add_subparsers(dest="command")

    # list
    lst = subparsers.add_parser("list", help="Show installed formulae and casks")
    lst.add_argument("--type", choices=["formula", "cask", "all"], default=None)
    lst.add_argument("--analytics", action="store_true",
                     help="Include analytics columns (cache-backed)")
    lst.add_argument("--fetch", action="store_true",
                     help="Fetch missing per-package analytics (implies --analytics)")
    lst.add_argument("--columns", metavar="SPEC")
    lst.add_argument("--limit", type=int, metavar="N")
    lst.add_argument("--json", action="store_true")

    # cache
    cache = subparsers.add_parser("cache", help="Inspect and manage the local cache")
    cache_sub = cache.add_subparsers(dest="cache_command", required=True)
    cache_sub.add_parser("status", help="Show cache path, age, counts, and lock state")
    refresh_p = cache_sub.add_parser("refresh", help="Refresh local cache data")
    refresh_p.add_argument("--force", action="store_true",
                           help="Refresh even when cache is fresh")
    cache_sub.add_parser("clear", help="Remove local cache files")

    # config
    config_p = subparsers.add_parser("config", help="Show configuration info")
    config_p.add_argument("config_sub_cmd", nargs="?", choices=["path"], default="path")

    return parser


def _normalize_argv(argv: list[str]) -> list[str]:
    if argv and argv[0] == "update-cache":
        return ["cache", "refresh", *argv[1:]]
    return argv


def _cmd_list(args: argparse.Namespace, cfg: dict) -> int:
    opts = options_mod.build_list_options(args, cfg)
    list_cols_cfg = cfg["list"]["columns"]

    try:
        col_defs = columns_mod.resolve(opts.columns_spec, list_cols_cfg)
    except ValueError as exc:
        print(f"brewq: {exc}", file=sys.stderr)
        return 1

    if opts.with_analytics or opts.fetch_analytics:
        keys = {c.key for c in col_defs}
        if "installs" not in keys and "installs_30d" not in keys:
            try:
                col_defs = col_defs + columns_mod.resolve("installs", [])
            except ValueError:
                pass

    try:
        from brewq import brew as brew_mod
        raw = brew_mod.info_installed()
    except FileNotFoundError as exc:
        print(f"brewq: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"brewq: failed to query installed packages: {exc}", file=sys.stderr)
        return 1

    from brewq.model import from_formula, from_cask
    packages = []
    for f in raw.get("formulae", []):
        packages.append(from_formula(f))
    for c in raw.get("casks", []):
        packages.append(from_cask(c))

    if opts.with_analytics or opts.fetch_analytics:
        _merge_cached_analytics(packages)

    packages = options_mod.rank_installed(packages, opts)

    if opts.json_output:
        render_mod.render_json(packages, col_defs, out=sys.stdout)
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
            pkg.installs_365d = cached_pkg.installs_365d


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


def _cmd_search(args: argparse.Namespace, cfg: dict) -> int:
    opts = options_mod.build_search_options(args, cfg)

    if not opts.query:
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

    ranked = options_mod.rank(packages, opts)

    if not ranked:
        print(f"No results for: {' '.join(opts.query)}", file=sys.stderr)
        return 0

    if opts.json_output:
        render_mod.render_json(ranked, col_defs, metric=opts.metric, out=sys.stdout)
    else:
        render_mod.render_table(ranked, col_defs, metric=opts.metric, out=sys.stdout)
    return 0


def _live_search(opts: options_mod.SearchOptions) -> list:
    try:
        from brewq import brew as brew_mod
        from brewq.model import from_formula, from_cask
        brew = shutil.which("brew")
        if not brew:
            return []
        result = subprocess.run(
            [brew, "search", "--", *opts.query],
            capture_output=True, text=True,
        )
        names = [
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip() and not line.startswith("==>")
        ]
        if not names:
            return []
        raw = brew_mod.info_packages(names[:30])
        packages = []
        for f in raw.get("formulae", []):
            packages.append(from_formula(f))
        for c in raw.get("casks", []):
            packages.append(from_cask(c))
        return packages
    except Exception:
        return []


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    raw_argv = _normalize_argv(raw_argv)

    cfg = config_mod.load()

    # Route to command parser if the first non-flag arg is a known command
    first_word = next((a for a in raw_argv if not a.startswith("-")), None)
    if first_word in _COMMANDS:
        args = _build_command_parser().parse_args(raw_argv)
        if args.command == "list":
            return _cmd_list(args, cfg)
        if args.command == "cache":
            return _cmd_cache(args, cfg)
        if args.command == "config":
            return _cmd_config(args)

    args = _build_search_parser().parse_args(raw_argv)
    return _cmd_search(args, cfg)


if __name__ == "__main__":
    raise SystemExit(main())
