from __future__ import annotations

import argparse
import os
import shlex
import subprocess
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
from brewq import spell

_ACTIONS = frozenset({"update", "setup", "config", "completion"})
_FORMATTER = argparse.RawDescriptionHelpFormatter


class _Parser(argparse.ArgumentParser):
    """Error first, then one usage line and a pointer to --help. No cache or network."""

    def parse_args(self, args=None, namespace=None):
        self._brewq_argv = list(sys.argv[1:] if args is None else args)
        return super().parse_args(args, namespace)

    def error(self, message: str) -> None:
        subs = getattr(self, "_brewq_subcommands", {})
        argv = getattr(self, "_brewq_argv", [])
        target = subs.get(argv[0], self) if argv else self
        option_argv = argv[:argv.index("--")] if "--" in argv else argv
        print(f"{_error_label(no_color='--no-color' in option_argv)}: {message}", file=sys.stderr)
        usage = " ".join(target.format_usage().split())
        if usage:
            print(usage, file=sys.stderr)
        print(f"see '{target.prog} --help'", file=sys.stderr)
        self.exit(2)


def _prog() -> str:
    name = Path(sys.argv[0]).name
    return name if name in {"brewq", "bq"} else "brewq"


def _error_label(*, no_color: bool = False) -> str:
    if not render_mod._use_color(sys.stderr, no_color=no_color):
        return "Error"
    return "\033[1mError\033[0m"
def _search_epilog() -> str:
    prog = _prog()
    return f"""\
actions: +update, +setup, +config [show|defaults|edit], +completion zsh
examples: {prog} ripgrep | {prog} -i | {prog} +update
alias: `brewq +setup` links the `bq` shorthand when the name is free
"""

_UPDATE_EPILOG = """\
Examples:
  brewq +update
  brewq +update --force
  brewq +update --offline
  brewq -u ripgrep
"""

_CONFIG_EPILOG = """\
Examples:
  brewq +config
  brewq +config show
  brewq +config defaults
  brewq +config edit

The config file controls default columns and cache freshness.
"""

_COLUMN_HELP = ",".join(columns_mod.CANONICAL_COLUMNS) + "; default"

_FULL_HELP_DETAILS = """\
columns:
{columns}

  Search default: name,90d,trend,desc
  Installed view (-i): name,desc
  Use one -c with a comma-separated list.
  Exact names only; duplicates keep their first occurrence.
  -c default,url appends URL to the configured view; -c url,default puts it first.
  Signed +x/-x edits are rejected.
  default can change between releases; scripts should list fields.

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
  `brewq +update` updates stale data; `brewq +update --force` updates now.
  `-u`/`--update` forces an update before the query. If it fails, the error goes
  to stderr and the query uses available local data, including the bundled seed.
  `-r` reverses the chosen order after `-t`, so the best row is last.
  `-a` removes the cap on terminal tables and puts the best row last, unless `-t` is given.
  Configured caps/reverse apply only to terminal tables; pipes/TSV need explicit flags.
  If analytics fail, counts from the previous user snapshot are retained and
  retried later.
  `brewq +config` shows effective configuration values and their sources.
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


def _add_top_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-t", "--top",
                        type=_positive_int, metavar="N",
                        help="show at most N rows, even with -a")


class _ColumnsAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest) is not None:
            raise argparse.ArgumentError(self, "specify columns once as a comma-separated list")
        setattr(namespace, self.dest, values)


def _add_column_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-c", "--columns", action=_ColumnsAction, metavar="COLS", help=_COLUMN_HELP)


def _add_reverse_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-r", "--reverse", action="store_true",
                        help="put the best rows last")


def _add_update_flag(parser: argparse.ArgumentParser, *, then: str) -> None:
    parser.add_argument("-u", "--update", action="store_true",
                        help=f"update the package register, then {then}")


def _add_color_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-n", "--no-color", action="store_true",
                        help="disable ANSI styling on stdout and stderr")


def _add_quiet_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="suppress routine status notes on stderr")


def _build_search_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog=_prog(),
        usage=f"{_prog()} [options] [query ...]",
        description="Search the local Homebrew catalog: compare install counts and trends, "
                    "inspect installed packages.",
        epilog=_search_epilog(),
        formatter_class=_FORMATTER,
    )
    parser.add_argument("query", nargs="*", help=argparse.SUPPRESS)
    parser.add_argument("-i", "--installed", action="store_true",
                        help="installed packages only; default columns name,desc")
    parser.add_argument("-s", "--sort", metavar="FIELD",
                        help=f"sort key: {options_mod.sort_choices_text()} (default: 90d)")
    _add_reverse_flag(parser)
    _add_top_flag(parser)
    parser.add_argument("-a", "--all", action="store_true",
                        help="show all matches, best rows last on a TTY")
    _add_column_flags(parser)
    parser.add_argument("-m", "--tsv", action="store_true",
                        help="tab-separated rows without a header")
    _add_color_flag(parser)
    _add_quiet_flag(parser)
    _add_update_flag(parser, then="search")
    parser.add_argument("-f", "--full-help", action="store_true",
                        help="show columns, trending, and cache behavior")
    parser.add_argument("-v", "--version", action=_VersionAction,
                        help="show program's version number and exit")
    return parser


def _build_command_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog=_prog(), formatter_class=_FORMATTER)
    subparsers = parser.add_subparsers(dest="command", parser_class=_Parser)
    parser._brewq_subcommands = subparsers.choices

    update_p = subparsers.add_parser(
        "+update",
        help="update the local package register",
        description="Update local Homebrew metadata and analytics.",
        epilog=_UPDATE_EPILOG,
        formatter_class=_FORMATTER,
    )
    update_mode = update_p.add_mutually_exclusive_group()
    update_mode.add_argument("--force", action="store_true",
                             help="update even when the register is fresh")
    update_mode.add_argument("--offline", action="store_true",
                             help="install the bundled catalog without contacting Homebrew")

    setup_p = subparsers.add_parser(
        "+setup",
        help="link bq when that command name is free",
        description="Link bq to this brewq if the name is not already taken.",
        formatter_class=_FORMATTER,
    )
    setup_p.add_argument("--remove", action="store_true",
                         help="remove brewq's own bq shortcut")
    setup_p.add_argument("--dry-run", action="store_true",
                         help="print the planned link or removal without changing anything")

    # config
    config_p = subparsers.add_parser(
        "+config",
        help="show, print defaults, or edit configuration",
        description="Show effective configuration, print defaults, or edit the config file.",
        epilog=_CONFIG_EPILOG,
        formatter_class=_FORMATTER,
    )
    config_commands = config_p.add_subparsers(dest="config_command", parser_class=_Parser)
    config_p._brewq_subcommands = config_commands.choices
    for name, description in (
        ("show", "show effective values and their sources (default)"),
        ("defaults", "print built-in defaults as TOML"),
        ("edit", "edit the config file and validate it"),
    ):
        child = config_commands.add_parser(name, help=description, description=description)
        _add_color_flag(child)

    completion_p = subparsers.add_parser(
        "+completion", help="generate shell completion", formatter_class=_FORMATTER,
    )
    completion_p.add_argument("shell", choices=["zsh"], help="completion shell")

    for subparser in subparsers.choices.values():
        _add_color_flag(subparser)

    return parser


def _full_help_text() -> str:
    details = _FULL_HELP_DETAILS.format(columns="\n".join(columns_mod.reference_lines()))
    return f"{_build_search_parser().format_help().rstrip()}\n\n{details.rstrip()}\n"


def _update_register(*, force: bool, quiet: bool = False) -> int:
    """Refresh before a query; report failures without preventing local reads."""
    if not quiet:
        print("Updating register...", file=sys.stderr)
    try:
        result = cache_mod.refresh(force=force)
    except Exception as exc:
        print(f"brewq: register update failed: {exc}", file=sys.stderr)
        return 1
    if result.outcome is cache_mod.RefreshOutcome.LOCKED:
        if not quiet:
            print("register: update already in progress; using available data", file=sys.stderr)
    elif result.outcome is cache_mod.RefreshOutcome.METADATA_ONLY:
        # A result-quality warning, not progress: quiet must not hide it.
        print(
            f"register: metadata updated; analytics incomplete ({result.analytics_error})",
            file=sys.stderr,
        )
    return 0


def _cmd_update(args: argparse.Namespace) -> int:
    if args.offline:
        path, formulae, casks = cache_mod.preload_bundled()
        print(f"cache: preloaded {formulae} formulae, {casks} casks at {path}")
        return 0
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
        print(shortcut.remove(brewq, brewq.parent, state, dry_run=args.dry_run))
        return 0
    block = shortcut.path_block(shutil_which("bq"), brewq, state, dry_run=args.dry_run)
    print(block or shortcut.ensure(
        brewq, brewq.parent, state, shortcut.shell_claim("bq"), dry_run=args.dry_run,
    ))
    return 0


def shutil_which(name: str) -> str | None:
    import shutil
    return shutil.which(name)


def _cmd_config(args: argparse.Namespace) -> int:
    if args.config_command == "defaults":
        print(config_mod.to_toml(config_mod.DEFAULTS), end="")
        return 0

    path = config_mod.config_path()
    if args.config_command == "edit":
        try:
            editor = shlex.split(os.environ.get("VISUAL") or os.environ.get("EDITOR") or "")
            if not editor:
                print("brewq: set VISUAL or EDITOR to edit configuration", file=sys.stderr)
                return 1
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with path.open("x", encoding="utf-8") as fh:
                    fh.write(config_mod.starter_toml())
            except FileExistsError:
                pass
            result = subprocess.run([*editor, str(path)], check=False)
        except (OSError, ValueError) as exc:
            print(f"brewq: config edit: {exc}", file=sys.stderr)
            return 1
        _, _, diagnostics = config_mod.validate()
        for message in diagnostics:
            print(message, file=sys.stderr)
        return result.returncode or int(bool(diagnostics))

    cfg, sources, diagnostics = config_mod.validate()
    for message in diagnostics:
        print(message, file=sys.stderr)
    cfg["cache"]["auto_refresh"] = config_mod.auto_refresh_enabled(cfg)
    if os.environ.get("BREWQ_NO_AUTO_REFRESH", "").strip().lower() in {"1", "true", "yes", "on"}:
        sources["auto-update"] = "BREWQ_NO_AUTO_REFRESH"
    print(f"# {path} ({'exists' if path.exists() else 'not found'})")
    print(config_mod.to_toml(cfg, sources), end="")
    return 0


def _cmd_search(args: argparse.Namespace, cfg: dict) -> int:
    try:
        opts = options_mod.build_search_options(args, cfg)
    except ValueError as exc:
        print(f"brewq: {exc}", file=sys.stderr)
        return 2

    default_cols = cfg["list"]["columns"] if opts.installed_only else cfg["output"]["columns"]
    try:
        col_defs = columns_mod.select(opts.columns_spec, default_cols, tsv=opts.tsv_output)
    except ValueError as exc:
        print(f"brewq: {exc}", file=sys.stderr)
        return 2

    if args.update:
        _update_register(force=True, quiet=args.quiet)

    loaded = _load_cache()
    if loaded is None:
        return 1
    packages = loaded.packages

    ranked = options_mod.rank(packages, opts)

    if not ranked:
        query_str = " ".join(opts.query) if opts.query else "(installed filter)"
        if not args.quiet:
            print(f"No results for: {query_str}", file=sys.stderr)
        _report_view_cap(0, opts.eligible_total, opts.top, quiet=args.quiet)
        _finish_cache_command(loaded, cfg, no_color=args.no_color, quiet=args.quiet)
        return 0

    # Config-only auto expands after ranking, including inside a mixed default list.
    metric = columns_mod.pick_representative_metric(ranked[0])
    col_defs = columns_mod.select(
        opts.columns_spec, default_cols, representative_metric=metric, tsv=opts.tsv_output,
    )

    shown = len(ranked)
    if opts.tsv_output:
        render_mod.render_tsv(ranked, col_defs, out=sys.stdout)
    else:
        named_columns = {key.strip() for key in args.columns.split(",")} if args.columns else set()
        result = render_mod.render_table(
            ranked,
            col_defs,
            out=sys.stdout,
            sorted_col=opts.sort,
            no_color=args.no_color,
            installed_only=opts.installed_only,
            auto_height=opts.auto_height,
            reverse=opts.reverse,
            named_columns=named_columns,
        )
        if not args.quiet:
            for key in result.hidden:
                if key in named_columns:
                    print(f"brewq: no {key} values in these results; column hidden", file=sys.stderr)
        shown = result.shown
    sys.stdout.flush()
    _report_view_cap(shown, opts.eligible_total, opts.top, quiet=args.quiet)
    _finish_cache_command(loaded, cfg, no_color=args.no_color, quiet=args.quiet)
    return 0


def _report_view_cap(shown: int, total: int, top: int, *, quiet: bool = False) -> None:
    """Disclose a cap that hid rows; stdout stays machine-clean."""
    if quiet or top <= 0 or shown >= total:
        return
    print(f"brewq: showing {shown} of {total}; -a for all, -t N for a count",
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


def _finish_cache_command(
    loaded: cache_mod.CacheLoad, cfg: dict, *, no_color: bool = False, quiet: bool = False,
) -> None:
    max_age = int(cfg["cache"]["max_age_seconds"])
    failure_detail = "unknown scheduler error"
    scheduler_state = "disabled"
    if config_mod.auto_refresh_enabled(cfg):
        try:
            scheduler_state = scheduler_mod.schedule_if_needed(loaded, max_age)
        except Exception as exc:
            scheduler_state = "failed"
            failure_detail = " ".join(str(exc).splitlines())[:120]
    if quiet:
        if not loaded.analytics_complete and loaded.source != "seed":
            render_mod.render_cache_note(
                f"cache: metadata {_format_age(loaded.age_seconds)} old; analytics incomplete",
                sys.stderr,
                no_color=no_color,
            )
        return

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
        render_mod.render_cache_note(f"cache: bundled seed{detail}", sys.stderr, no_color=no_color)
        return

    age_str = _format_age(loaded.age_seconds)
    if not loaded.analytics_complete:
        detail = f"; {suffix}" if suffix else ""
        render_mod.render_cache_note(
            f"cache: metadata {age_str} old; analytics incomplete{detail}",
            sys.stderr,
            no_color=no_color,
        )
    elif loaded.requires_refresh or loaded.age_seconds >= max_age:
        detail = f"; {suffix}" if suffix else ""
        render_mod.render_cache_note(f"cache: {age_str} old{detail}", sys.stderr, no_color=no_color)
    else:
        render_mod.render_cache_note(f"cache: {age_str} old", sys.stderr, no_color=no_color)


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
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        # Reader closed early (`brewq ... | head`): exit like SIGPIPE, without a traceback
        # or a second error when the interpreter flushes stdout at shutdown.
        import os

        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except (OSError, ValueError):
            pass
        return 141


def _join_column_edits(argv: list[str]) -> list[str]:
    normalized = []
    tokens = iter(argv)
    for token in tokens:
        if token == "--":
            normalized.extend([token, *tokens])
            break
        if token in {"-c", "--columns"} and (value := next(tokens, None)) is not None:
            if value.startswith("-") and value != "--":
                normalized.append(f"--columns={value}")
            else:
                normalized.extend([token, value])
            if value == "--":
                normalized.extend(tokens)
                break
        else:
            normalized.append(token)
    return normalized


def _main(argv: Sequence[str] | None = None) -> int:
    raw_argv = _join_column_edits(list(argv) if argv is not None else sys.argv[1:])
    parser = _build_search_parser()
    parser._brewq_argv = raw_argv
    if raw_argv == ["--_complete"]:
        sys.stdout.write("".join(f"{name}\n" for name in cache_mod.completion_names()))
        return 0

    # Route subcommands only when they are the first token. Search remains the
    # default command even when query terms are named like subcommands.
    if raw_argv and raw_argv[0].startswith("+") and raw_argv[0][1:] in _ACTIONS:
        parser = _build_command_parser()
        parser._brewq_subcommands[raw_argv[0]]._brewq_argv = raw_argv
        args = parser.parse_args(raw_argv)
        if args.command == "+update":
            return _cmd_update(args)
        if args.command == "+setup":
            return _cmd_setup(args)
        if args.command == "+config":
            return _cmd_config(args)
        if args.command == "+completion":
            from brewq.completion import zsh_script

            print(zsh_script(_build_search_parser(), _build_command_parser()), end="")
            return 0

    if raw_argv and raw_argv[0].startswith("+") and raw_argv[0] != "+":
        action = raw_argv[0]
        choices = sorted("+" + name for name in _ACTIONS)
        parser.error(f"unknown action {action}.{spell.suggestion(action, choices)}")

    # Flags may sit between query terms. Actions are +tokens, never bare words.
    args = parser.parse_intermixed_args(raw_argv)
    if args.full_help:
        print(_full_help_text(), end="")
        return 0
    cfg = config_mod.load()
    return _cmd_search(args, cfg)


if __name__ == "__main__":
    raise SystemExit(main())
