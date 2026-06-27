#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import statistics
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


@dataclass(frozen=True)
class Case:
    name: str
    command: str
    argv: tuple[str, ...]


@dataclass(frozen=True)
class Summary:
    name: str
    iterations: int
    min_ms: float
    median_ms: float
    mean_ms: float
    max_ms: float
    failures: int
    command: str


def _python(*args: str) -> tuple[str, ...]:
    return (sys.executable, *args)


def _brewq(*args: str) -> tuple[str, ...]:
    return _python("-m", "brewq.cli", *args)


CASES: tuple[Case, ...] = (
    Case(
        "cache_load",
        "python -c 'from brewq import cache; print(len(cache.load_packages()))'",
        _python("-c", "from brewq import cache; print(len(cache.load_packages()))"),
    ),
    Case(
        "rank_filter",
        "python -c 'load cache and rank json top 10'",
        _python(
            "-c",
            "from brewq import cache, options; "
            "pkgs=cache.load_packages(); "
            "opts=options.SearchOptions(query=['json'], sort='installs_30d', limit=10); "
            "print(len(options.rank(pkgs, opts)))",
        ),
    ),
    Case(
        "search_table",
        "brewq -t 10 json",
        _brewq("-t", "10", "json"),
    ),
    Case(
        "search_tsv",
        "brewq --tsv -c name,30d ripgrep",
        _brewq("--tsv", "-c", "name,30d", "ripgrep"),
    ),
    Case(
        "search_wide",
        "brewq -t 10 -c name,type,version,30d,90d,365d,status,description rust",
        _brewq("-t", "10", "-c", "name,type,version,30d,90d,365d,status,description", "rust"),
    ),
    Case(
        "list_default",
        "brewq list --limit 25",
        _brewq("list", "--limit", "25"),
    ),
    Case(
        "list_analytics",
        "brewq list --analytics --limit 25",
        _brewq("list", "--analytics", "--limit", "25"),
    ),
    Case(
        "list_tsv",
        "brewq list --tsv -c name,type,version --limit 25",
        _brewq("list", "--tsv", "-c", "name,type,version", "--limit", "25"),
    ),
)


def _env() -> dict[str, str]:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC) if not existing else f"{SRC}{os.pathsep}{existing}"
    return env


def select_cases(names: Sequence[str] | None = None) -> list[Case]:
    if not names:
        return list(CASES)
    by_name = {case.name: case for case in CASES}
    selected: list[Case] = []
    for name in names:
        case = by_name.get(name)
        if case is None:
            valid = ", ".join(sorted(by_name))
            raise ValueError(f"Unknown benchmark case {name!r}. Valid: {valid}")
        selected.append(case)
    return selected


def summarize_times(name: str, elapsed_seconds: Sequence[float], failures: int) -> Summary:
    if not elapsed_seconds:
        return Summary(name, 0, 0.0, 0.0, 0.0, 0.0, failures, "")
    elapsed_ms = [round(value * 1000, 1) for value in elapsed_seconds]
    return Summary(
        name=name,
        iterations=len(elapsed_ms),
        min_ms=min(elapsed_ms),
        median_ms=round(statistics.median(elapsed_ms), 1),
        mean_ms=round(statistics.mean(elapsed_ms), 1),
        max_ms=max(elapsed_ms),
        failures=failures,
        command="",
    )


def run_case(case: Case, iterations: int, warmups: int, timeout: float) -> Summary:
    env = _env()
    failures = 0
    elapsed: list[float] = []
    total_runs = warmups + iterations
    for index in range(total_runs):
        started = time.perf_counter()
        result = subprocess.run(
            case.argv,
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        finished = time.perf_counter()
        if result.returncode != 0:
            failures += 1
        if index >= warmups:
            elapsed.append(finished - started)
    summary = summarize_times(case.name, elapsed, failures)
    return Summary(
        name=summary.name,
        iterations=summary.iterations,
        min_ms=summary.min_ms,
        median_ms=summary.median_ms,
        mean_ms=summary.mean_ms,
        max_ms=summary.max_ms,
        failures=summary.failures,
        command=case.command,
    )


def _ms(value: float) -> str:
    return f"{value:.1f}ms"


def format_markdown_table(summaries: Sequence[Summary]) -> str:
    lines = [
        "| case | iters | min | median | mean | max | failures | command |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in summaries:
        lines.append(
            f"| {item.name} | {item.iterations} | {_ms(item.min_ms)} | "
            f"{_ms(item.median_ms)} | {_ms(item.mean_ms)} | {_ms(item.max_ms)} | "
            f"{item.failures} | `{item.command}` |"
        )
    return "\n".join(lines)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark important brewq paths.")
    parser.add_argument("-n", "--iterations", type=int, default=3,
                        help="Measured iterations per case [default: 3]")
    parser.add_argument("-w", "--warmups", type=int, default=1,
                        help="Unmeasured warmup runs per case [default: 1]")
    parser.add_argument("--timeout", type=float, default=90.0,
                        help="Timeout per command in seconds [default: 90]")
    parser.add_argument("--case", action="append", dest="cases",
                        help="Case name to run; repeat to choose multiple")
    parser.add_argument("--list", action="store_true",
                        help="List benchmark cases and exit")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(list(argv) if argv is not None else sys.argv[1:])
    if args.list:
        for case in CASES:
            print(f"{case.name}\t{case.command}")
        return 0
    if args.iterations < 1:
        print("benchmark: --iterations must be >= 1", file=sys.stderr)
        return 2
    if args.warmups < 0:
        print("benchmark: --warmups must be >= 0", file=sys.stderr)
        return 2
    try:
        cases = select_cases(args.cases)
    except ValueError as exc:
        print(f"benchmark: {exc}", file=sys.stderr)
        return 2

    summaries = [
        run_case(case, iterations=args.iterations, warmups=args.warmups, timeout=args.timeout)
        for case in cases
    ]
    print(format_markdown_table(summaries))
    return 1 if any(summary.failures for summary in summaries) else 0


if __name__ == "__main__":
    raise SystemExit(main())
