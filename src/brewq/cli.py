from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from brewq import cache as cache_mod
from brewq import columns as columns_mod
from brewq import config as config_mod
from brewq import options as options_mod
from brewq import render as render_mod

_COMMANDS = frozenset({"list", "refresh", "config", "random"})
_FORMATTER = argparse.RawDescriptionHelpFormatter
_COLOR_RED = "\033[31m"
_RESET = "\033[0m"

_SEARCH_EPILOG = """\
Examples:
  brewq ripgrep
  brewq -t 10 json
  brewq -s 365d rust
  brewq terminal multiplexer

Commands: list  refresh  config
"""

_LIST_EPILOG = """\
Examples:
  brewq list
  brewq list -p full
  brewq list -c name,type,version
"""

_REFRESH_EPILOG = """\
Examples:
  brewq refresh
  brewq refresh --force
  brewq -r ripgrep

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
                        help="Sort by: 30d (i30), 90d (i90), 365d (i365), name  [default: 30d]")
    parser.add_argument("-l", "--installed", action="store_true",
                        help="Filter to installed packages")
    parser.add_argument("-p", "--preset", metavar="NAME",
                        help="Column preset: compact, full")
    parser.add_argument("-c", "--columns", metavar="KEYS",
                        help="Columns: name (n), 30d, 90d, 365d, pop, bin, type (t), version (v), desc (d), inst (i), status, url (h)")
    parser.add_argument("-t", "--top", type=int, metavar="N",
                        help="Show top N by installs")
    parser.add_argument("-r", "--refresh", action="store_true",
                        help="Refresh cache before searching")
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
    lst.add_argument("-p", "--preset", metavar="NAME",
                     help="Column preset: compact, full")
    lst.add_argument("-c", "--columns", metavar="KEYS",
                     help="Explicit columns: comma-joined keys")
    lst.add_argument("--limit", type=int, metavar="N")
    lst.add_argument("--tsv", action="store_true",
                     help="Output raw tab-separated rows for shell scripting")

    # refresh
    refresh_p = subparsers.add_parser(
        "refresh",
        help="Refresh local cache data",
        description="Refresh local Homebrew metadata and analytics cache.",
        epilog=_REFRESH_EPILOG,
        formatter_class=_FORMATTER,
    )
    refresh_p.add_argument("--force", action="store_true",
                           help="Refresh even when cache is fresh")

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
        return ["refresh", *argv[1:]]
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

    if opts.with_analytics:
        col_defs = _ensure_list_analytics_column(col_defs)

    _print_cache_age(cfg)
    packages = [p for p in cache_mod.load_packages() if p.installed]

    packages = options_mod.rank_installed(packages, opts)

    if opts.tsv_output:
        render_mod.render_tsv(packages, col_defs, out=sys.stdout)
    else:
        render_mod.render_table(packages, col_defs, out=sys.stdout)
    return 0


def _ensure_list_analytics_column(col_defs: list) -> list:
    keys = {c.key for c in col_defs}
    if keys & {"installs_30d", "installs_90d", "installs_365d"}:
        return col_defs
    installs_col = columns_mod.resolve("installs_30d", [])[0]
    desc_idx = next((i for i, col in enumerate(col_defs) if col.key == "description"), None)
    if desc_idx is None:
        return [*col_defs, installs_col]
    return [*col_defs[:desc_idx], installs_col, *col_defs[desc_idx:]]


def _cmd_refresh(args: argparse.Namespace) -> int:
    force = getattr(args, "force", False)
    print("Refreshing cache...", file=sys.stderr)
    try:
        cache_mod.refresh(force=force)
        s = cache_mod.status()
        print(
            f"cache: {_format_age(s.get('age_seconds'))} old; "
            f"{s['formula_count']} formulae, {s['cask_count']} casks",
            file=sys.stderr,
        )
    except Exception as exc:
        print(f"brewq: cache refresh failed: {exc}", file=sys.stderr)
        return 1
    return 0


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
        refresh=False,
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

    if getattr(args, "refresh", False):
        try:
            print("Refreshing cache...", file=sys.stderr)
            cache_mod.refresh(force=True)
        except Exception as exc:
            print(f"brewq: cache refresh failed: {exc}", file=sys.stderr)
            return 1

    _print_cache_age(cfg)
    packages = cache_mod.load_packages()

    if not packages:
        print(
            "Cache not built yet. Run `brewq refresh`.",
            file=sys.stderr,
        )

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


def _format_age(age_seconds: object) -> str:
    if age_seconds is None:
        return "missing"
    age = max(0, int(age_seconds))
    if age < 60:
        return f"{age}s"
    if age < 3600:
        return f"{age // 60}m"
    if age < 172800:
        return f"{age // 3600}h"
    return f"{age // 86400}d"


def _stderr_uses_color() -> bool:
    return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()


def _print_cache_age(cfg: dict) -> None:
    age = cache_mod.age_seconds()
    if age is None:
        print("cache: missing; run `brewq refresh`", file=sys.stderr)
        return

    max_age = int(cfg["cache"]["max_age_seconds"])
    age_text = _format_age(age)
    if int(age) >= max_age:
        text = f"cache: stale, {age_text} old; run `brewq refresh`"
        if _stderr_uses_color():
            text = f"{_COLOR_RED}{text}{_RESET}"
        print(text, file=sys.stderr)
        return

    print(f"cache: {age_text} old", file=sys.stderr)


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
        if args.command == "refresh":
            return _cmd_refresh(args)
        if args.command == "config":
            return _cmd_config(args)
        if args.command == "random":
            return _cmd_random(args, cfg)

    args = _build_search_parser().parse_args(raw_argv)
    return _cmd_search(args, cfg)


if __name__ == "__main__":
    raise SystemExit(main())
