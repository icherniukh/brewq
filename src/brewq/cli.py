from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from brewq import cache as cache_mod
from brewq import columns as columns_mod
from brewq import config as config_mod
from brewq import options as options_mod
from brewq import render as render_mod
from brewq import scheduler as scheduler_mod
from brewq import seed as seed_mod

_COMMANDS = frozenset({"list", "update", "setup", "config", "random", "completion"})
_FORMATTER = argparse.RawDescriptionHelpFormatter


class _Parser(argparse.ArgumentParser):
    """Help first, then a visually separated error. No cache or network."""

    def parse_args(self, args=None, namespace=None):
        self._brewq_argv = list(sys.argv[1:] if args is None else args)
        return super().parse_args(args, namespace)

    def error(self, message: str) -> None:
        subs = getattr(self, "_brewq_subcommands", {})
        argv = getattr(self, "_brewq_argv", [])
        target = subs.get(argv[0], self) if argv else self
        target.print_help(sys.stderr)
        print(file=sys.stderr)
        print(f"{_error_label()}: {message}", file=sys.stderr)
        self.exit(2)


def _prog() -> str:
    name = Path(sys.argv[0]).name
    return name if name in {"brewq", "bq"} else "brewq"


def _error_label() -> str:
    if not sys.stderr.isatty() or os.environ.get("NO_COLOR", "") or os.environ.get("TERM") == "dumb":
        return "Error"
    return "\033[1mError\033[0m"
_SEARCH_EPILOG = """\
commands: list, update, config path, completion zsh
examples: brewq ripgrep | brewq -t 10 rust | brewq -u ripgrep
"""

_LIST_EPILOG = """\
Use `brewq --full-help` for columns, trending, and cache behavior.
"""

_UPDATE_EPILOG = """\
Examples:
  brewq update
  brewq update --force
  brewq -u ripgrep

refresh and update-cache remain aliases. BREWQ_NO_REVERSE=1 disables reverse sort.
"""

_CONFIG_EPILOG = """\
Examples:
  brewq config path

The config file controls default columns and cache freshness.
"""

_COLUMN_HELP = "fields, +add, -remove, all; -c help lists fields"

_FULL_HELP_DETAILS = """\
advanced search:
  --all               include deprecated and disabled packages
  -r, --refresh       alias for -u/--update
  --url               add the URL column; prefer -c +url

columns:
{columns}

  Short forms: 30d, 90d, 365d, trend, bin, desc, home.
  Search default: name,90d,trending,description
  Installed view (-i or list): name,description
  Use -c help for fields and examples. -c +version,bin adds to your layout;
  -c +home,-trend adds homepage and removes trend; -c all shows every field.

trending:
  TREND compares a package's recent monthly install rate with its own earlier
  monthly rate. With complete data, recent is 90d / 3 and earlier is the prior
  275 days normalized to 30 days. Low-volume and newly tracked packages are
  smoothed toward 1.0x; 1.0x means steady. Missing history displays `-`.
  Table cues: ↑↑ >= 2x, ↑ >= 1.2x, · near baseline, ↓ < 0.8x.
  TREND measures momentum, not absolute popularity; search sorts by 90d unless
  another field is selected.

cache:
  A bundled seed makes the first query immediate. Fresh snapshots are read
  locally. Stale data is shown immediately, then updated in the background.
  `brewq update` updates stale data; `brewq update --force` updates now.
  `-R` reverses the chosen order after `-t`, so the best row is last.
  It is off unless `-R` or `[search] reverse` asks for it. `BREWQ_NO_REVERSE=1`
  turns it off immediately, even when the flag or config enables it.
  If analytics fail, counts from the previous user snapshot are retained and
  retried later.
  `brewq config path` shows the configuration file.
"""


class _VersionAction(argparse.Action):
    """Print the version on demand; looking it up eagerly slows every run."""

    def __init__(self, option_strings, dest=argparse.SUPPRESS, default=argparse.SUPPRESS, help=None):
        super().__init__(option_strings, dest, default=default, nargs=0, help=help)

    def __call__(self, parser, namespace, values, option_string=None):
        import brewq

        print(f"brewq {brewq.__version__}")
        parser.exit()


def _positive_int(raw: str) -> int:
    value = int(raw)
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


def _add_limit_flag(parser: argparse.ArgumentParser, *, dest: str) -> None:
    parser.add_argument("-t", "--top", "--limit", dest=dest,
                        type=_positive_int, metavar="N",
                        help="show at most N packages")


def _add_column_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-c", "--columns", metavar="COLS", help=_COLUMN_HELP)
    parser.add_argument("--url", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("-v", "--verbose", action="store_true",
                        help=argparse.SUPPRESS)


def _add_reverse_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-R", "--reverse", action=argparse.BooleanOptionalAction,
                        default=None,
                        help="reverse sort order so the best rows are last")


def _add_update_flag(parser: argparse.ArgumentParser, *, then: str) -> None:
    parser.add_argument("-u", "--update", action="store_true",
                        help=f"update the package register, then {then}")
    parser.add_argument("-r", "--refresh", action="store_true", help=argparse.SUPPRESS)


def _build_search_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog=_prog(),
        usage=f"{_prog()} [options] [query ...]\n       {_prog()} {{list,update,config,completion}} ...",
        description="Fast, read-only Homebrew package search.",
        epilog=_SEARCH_EPILOG,
        formatter_class=_FORMATTER,
    )
    parser.add_argument("query", nargs="*", help=argparse.SUPPRESS)
    parser.add_argument("-s", "--sort", metavar="FIELD",
                        help=f"sort by {options_mod.sort_choices_text()} (default: 90d)")
    _add_reverse_flag(parser)
    _add_limit_flag(parser, dest="top")
    parser.add_argument("-i", "--installed", action="store_true",
                        help="search installed packages only")
    parser.add_argument("--all", action="store_true", help=argparse.SUPPRESS)
    _add_column_flags(parser)
    _add_update_flag(parser, then="search")
    parser.add_argument("--tsv", action="store_true",
                        help="tab-separated rows without a header")
    parser.add_argument("--full-help", action="store_true",
                        help="show columns, trending, and cache behavior")
    parser.add_argument("--version", action=_VersionAction,
                        help="show program's version number and exit")
    return parser


def _build_command_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog=_prog(), formatter_class=_FORMATTER)
    subparsers = parser.add_subparsers(dest="command", parser_class=_Parser)
    parser._brewq_subcommands = subparsers.choices

    # list
    lst = subparsers.add_parser(
        "list",
        help="Show installed formulae and casks",
        usage="brewq list [options]",
        description="Show installed formulae and casks.",
        epilog=_LIST_EPILOG,
        formatter_class=_FORMATTER,
    )
    lst.add_argument("--analytics", action="store_true",
                     help=argparse.SUPPRESS)
    _add_reverse_flag(lst)
    _add_column_flags(lst)
    _add_update_flag(lst, then="list")
    _add_limit_flag(lst, dest="limit")
    lst.add_argument("--tsv", action="store_true",
                     help="tab-separated output for scripting")

    update_p = subparsers.add_parser(
        "update",
        help="Update the local package register",
        description="Update local Homebrew metadata and analytics.",
        epilog=_UPDATE_EPILOG,
        formatter_class=_FORMATTER,
    )
    update_p.add_argument("--force", action="store_true",
                          help="Update even when the register is fresh")

    setup_p = subparsers.add_parser(
        "setup",
        help="Link bq when that command name is free",
        description="Link bq to this brewq if the name is not already taken.",
        formatter_class=_FORMATTER,
    )
    setup_p.add_argument("--remove", action="store_true",
                         help="Remove brewq's own bq shortcut")

    # config
    config_p = subparsers.add_parser(
        "config",
        help="Show configuration info",
        description="Show where brewq reads configuration.",
        epilog=_CONFIG_EPILOG,
        formatter_class=_FORMATTER,
    )
    config_p.add_argument("config_sub_cmd", nargs="?", choices=["path"], default="path",
                          help="Print the config file path")

    completion_p = subparsers.add_parser(
        "completion", help="Generate shell completion", formatter_class=_FORMATTER,
    )
    completion_p.add_argument("shell", choices=["zsh"], help="Completion shell")

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


def _full_help_text() -> str:
    details = _FULL_HELP_DETAILS.format(columns="\n".join(columns_mod.reference_lines()))
    return f"{_build_search_parser().format_help().rstrip()}\n\n{details.rstrip()}\n"


def _normalize_argv(argv: list[str]) -> list[str]:
    if argv and argv[0] in {"update-cache", "refresh"}:
        return ["update", *argv[1:]]
    return argv


def _explicit_update(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "update", False) or getattr(args, "refresh", False))


def _validate_column_flags(args: argparse.Namespace) -> str | None:
    """Return an error string if -c and -v are both set, else None."""
    if getattr(args, "columns", None) and getattr(args, "verbose", False):
        return "cannot use both -c/--columns and -v/--verbose"
    return None


def _apply_column_shortcuts(args: argparse.Namespace, col_defs: list) -> list:
    if getattr(args, "url", False):
        col_defs = columns_mod.with_url(col_defs)
    return col_defs


def _cmd_list(args: argparse.Namespace, cfg: dict) -> int:
    err = _validate_column_flags(args)
    if err:
        print(f"brewq: {err}", file=sys.stderr)
        return 1

    opts = options_mod.build_list_options(args, cfg)
    list_cols_cfg = cfg["list"]["columns"]

    try:
        col_defs = columns_mod.select(opts.columns_spec, list_cols_cfg)
    except ValueError as exc:
        print(f"brewq: {exc}", file=sys.stderr)
        return 1

    col_defs = _apply_column_shortcuts(args, col_defs)

    if _explicit_update(args) and (failed := _update_register(force=True)):
        return failed

    if opts.with_analytics:
        col_defs = _ensure_list_analytics_column(col_defs)

    loaded = _load_cache()
    if loaded is None:
        return 1
    packages = [p for p in loaded.packages if p.installed]

    packages = options_mod.rank_installed(packages, opts)

    if opts.tsv_output:
        render_mod.render_tsv(packages, col_defs, out=sys.stdout)
    else:
        render_mod.render_table(packages, col_defs, out=sys.stdout)
    sys.stdout.flush()
    _report_view_cap(len(packages), opts.eligible_total, opts.limit)
    _finish_cache_command(loaded, cfg)
    return 0


def _ensure_list_analytics_column(col_defs: list) -> list:
    keys = {c.key for c in col_defs}
    if "installs_90d" in keys:
        return col_defs
    installs_col = columns_mod.resolve("installs_90d", [])[0]
    desc_idx = next((i for i, col in enumerate(col_defs) if col.key == "description"), None)
    if desc_idx is None:
        return [*col_defs, installs_col]
    return [*col_defs[:desc_idx], installs_col, *col_defs[desc_idx:]]


def _update_register(*, force: bool) -> int:
    """Update the register. Return 0 to continue, or a nonzero exit code."""
    print("Updating register...", file=sys.stderr)
    try:
        result = cache_mod.refresh(force=force)
    except Exception as exc:
        print(f"brewq: register update failed: {exc}", file=sys.stderr)
        return 1
    if result.outcome is cache_mod.RefreshOutcome.LOCKED:
        print("register: update already in progress; using available data", file=sys.stderr)
    elif result.outcome is cache_mod.RefreshOutcome.METADATA_ONLY:
        print(
            f"register: metadata updated; analytics incomplete ({result.analytics_error})",
            file=sys.stderr,
        )
    return 0


def _cmd_update(args: argparse.Namespace) -> int:
    print("Updating register...", file=sys.stderr)
    try:
        result = cache_mod.refresh(force=getattr(args, "force", False))
    except Exception as exc:
        print(f"brewq: register update failed: {exc}", file=sys.stderr)
        return 1
    return _report_update_result(result)


def _report_update_result(result: cache_mod.RefreshResult) -> int:
    if result.outcome is cache_mod.RefreshOutcome.FRESH:
        print("register: already fresh", file=sys.stderr)
        return 0
    if result.outcome is cache_mod.RefreshOutcome.LOCKED:
        print("register: update already in progress", file=sys.stderr)
        return 1
    if result.outcome is cache_mod.RefreshOutcome.METADATA_ONLY:
        print(
            f"register: metadata updated; analytics incomplete ({result.analytics_error})",
            file=sys.stderr,
        )
        return 1
    status = cache_mod.status()
    print(
        f"register: updated; {status['formula_count']} formulae, {status['cask_count']} casks",
        file=sys.stderr,
    )
    return 0


def _cmd_setup(args: argparse.Namespace) -> int:
    from brewq import shortcut

    invoked = Path(sys.argv[0])
    # Link beside the invoked shim. Resolving first would hide the shortcut inside the tool env.
    brewq = invoked if invoked.name in {"brewq", "bq"} and invoked.exists() else None
    if brewq is None:
        found = shutil_which("brewq")
        if found is None:
            print("brewq: setup could not find the brewq executable", file=sys.stderr)
            return 1
        brewq = Path(found)
    state = config_mod.cache_dir() / "shortcut.json"
    if args.remove:
        print(shortcut.remove(brewq, brewq.parent, state))
        return 0
    block = shortcut.path_block(shutil_which("bq"), brewq, state)
    print(block or shortcut.ensure(brewq, brewq.parent, state, shortcut.shell_claim("bq")))
    return 0


def shutil_which(name: str) -> str | None:
    import shutil
    return shutil.which(name)


def _cmd_config(args: argparse.Namespace) -> int:
    print(config_mod.config_path())
    return 0


_RANDOM_TERMS = (
    "json", "http", "markdown", "terminal", "pdf", "video",
    "image", "database", "git", "compress", "encrypt", "monitor",
    "search", "diff", "sync", "backup", "proxy", "log", "parser",
    "fuzzy", "render", "stream", "lint", "format", "test",
)
_RANDOM_SORTS = ("trending", "trending", "30d", "365d", "90d", "name")
_RANDOM_LAYOUTS = (
    None,  # default columns
    "name,30d,90d,365d,description",
    "name,type,version,bin,description",
    "name,30d,url",
)


def _cmd_random(args: argparse.Namespace, cfg: dict) -> int:
    import random as random_mod

    rng = random_mod.Random(getattr(args, "seed", None))
    query = rng.choice(_RANDOM_TERMS)
    sort = rng.choice(_RANDOM_SORTS)
    top = rng.randint(4, 10)
    columns = rng.choice(_RANDOM_LAYOUTS)

    command = ["brewq", "-t", str(top), "-s", sort]
    if columns:
        command.extend(["-c", columns])
    command.append(query)
    print(" ".join(command), file=sys.stderr)

    search_args = argparse.Namespace(
        query=[query],
        sort=sort,
        installed=False,
        columns=columns,
        url=False,
        verbose=False,
        top=top,
        update=False,
        refresh=False,
        reverse=None,
        tsv=False,
        all=False,
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

    default_cols = cfg["list"]["columns"] if opts.installed_only else cfg["output"]["columns"]
    col_defs = None
    if opts.columns_spec != "default":
        # "default" is resolved after ranking: it may contain "auto", which needs
        # the top result to pick a representative raw metric column.
        try:
            if isinstance(opts.columns_spec, str) and opts.columns_spec.strip().startswith(("+", "-")):
                columns_mod.parse_edits(opts.columns_spec)
            else:
                col_defs = columns_mod.select(opts.columns_spec, default_cols)
        except ValueError as exc:
            print(f"brewq: {exc}", file=sys.stderr)
            return 1

    if _explicit_update(args) and (failed := _update_register(force=True)):
        return failed

    loaded = _load_cache()
    if loaded is None:
        return 1
    packages = loaded.packages

    ranked = options_mod.rank(packages, opts)

    if not ranked:
        query_str = " ".join(opts.query) if opts.query else "(installed filter)"
        print(f"No results for: {query_str}", file=sys.stderr)
        _finish_cache_command(loaded, cfg)
        return 0

    if col_defs is None:
        metric = columns_mod.pick_representative_metric(ranked[0])
        try:
            col_defs = columns_mod.select(opts.columns_spec, default_cols, representative_metric=metric)
        except ValueError as exc:
            print(f"brewq: {exc}", file=sys.stderr)
            return 1

    col_defs = _apply_column_shortcuts(args, col_defs)

    if opts.tsv_output:
        render_mod.render_tsv(ranked, col_defs, out=sys.stdout)
    else:
        render_mod.render_table(
            ranked,
            col_defs,
            out=sys.stdout,
            sorted_col=opts.sort,
        )
    sys.stdout.flush()
    _report_view_cap(len(ranked), opts.eligible_total, opts.limit)
    _finish_cache_command(loaded, cfg)
    return 0


def _report_view_cap(shown: int, total: int, limit: int) -> None:
    """Disclose a positive explicit/configured cap; stdout stays machine-clean."""
    if limit <= 0 or shown >= total:
        return
    print(f"brewq: showing {shown} of {total}; raise -t/--top or clear output.limit",
          file=sys.stderr)


def _load_cache() -> cache_mod.CacheLoad | None:
    try:
        return cache_mod.load()
    except seed_mod.SeedError:
        print("Initializing local package metadata...", file=sys.stderr)
        try:
            return cache_mod.foreground_bootstrap(timeout=60)
        except Exception as exc:
            print(f"brewq: initial cache bootstrap failed: {exc}", file=sys.stderr)
            return None


def _finish_cache_command(loaded: cache_mod.CacheLoad, cfg: dict) -> None:
    max_age = int(cfg["cache"]["max_age_seconds"])
    failure_detail = "unknown scheduler error"
    scheduler_state = "disabled"
    if config_mod.auto_refresh_enabled(cfg):
        try:
            scheduler_state = scheduler_mod.schedule_if_needed(loaded, max_age)
        except Exception as exc:
            scheduler_state = "failed"
            failure_detail = " ".join(str(exc).splitlines())[:120]

    suffixes = {
        "scheduled": "update scheduled",
        "pending": "update pending",
        "cooldown": "update deferred (cooldown)",
        "deferred": "update deferred",
        "failed": f"update not scheduled ({failure_detail})",
    }
    suffix = suffixes.get(scheduler_state)

    if loaded.source == "seed":
        detail = f"; {suffix}" if suffix else ""
        render_mod.render_cache_note(f"cache: bundled seed{detail}", sys.stderr)
        return

    age_str = _format_age(loaded.age_seconds)
    if not loaded.analytics_complete:
        detail = f"; {suffix}" if suffix else ""
        render_mod.render_cache_note(
            f"cache: metadata {age_str} old; analytics incomplete{detail}",
            sys.stderr,
        )
    elif loaded.requires_refresh or loaded.age_seconds >= max_age:
        detail = f"; {suffix}" if suffix else ""
        render_mod.render_cache_note(f"cache: {age_str} old{detail}", sys.stderr)
    else:
        render_mod.render_cache_note(f"cache: {age_str} old", sys.stderr)


def _format_age(age_seconds: object) -> str:
    if age_seconds is None:
        return "missing"
    age = max(0, int(age_seconds))
    if age < 60:
        return f"{age}s"
    if age < 3600:
        return f"{age // 60}min"
    if age < 172800:
        return f"{age // 3600}h"
    return f"{age // 86400}d"


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return _main(argv)
    except BrokenPipeError:
        # Reader closed early (`brewq ... | head`): exit like SIGPIPE, without a traceback
        # or a second error when the interpreter flushes stdout at shutdown.
        import os

        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except (OSError, ValueError):
            pass
        return 141


def _main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    raw_argv = _normalize_argv(raw_argv)
    if raw_argv == ["--_complete"]:
        sys.stdout.write("".join(f"{name}\n" for name in cache_mod.completion_names()))
        return 0

    # Route subcommands only when they are the first token. Search remains the
    # default command even when query terms are named like subcommands.
    if raw_argv and raw_argv[0] in _COMMANDS:
        args = _build_command_parser().parse_args(raw_argv)
        if args.command == "update":
            return _cmd_update(args)
        if args.command == "setup":
            return _cmd_setup(args)
        if args.command == "config":
            return _cmd_config(args)
        if args.command == "completion":
            from brewq.completion import zsh_script

            print(zsh_script(_build_search_parser(), _build_command_parser()), end="")
            return 0
        if getattr(args, "columns", None) == "help":
            print(columns_mod.selection_help(), end="")
            return 0
        cfg = config_mod.load()
        if args.command == "list":
            return _cmd_list(args, cfg)
        if args.command == "random":
            return _cmd_random(args, cfg)

    # Flags may sit between query terms. Subcommands stay first-token only.
    args = _build_search_parser().parse_intermixed_args(raw_argv)
    if args.full_help:
        print(_full_help_text(), end="")
        return 0
    if args.columns == "help":
        print(columns_mod.selection_help(), end="")
        return 0
    cfg = config_mod.load()
    return _cmd_search(args, cfg)


if __name__ == "__main__":
    raise SystemExit(main())
