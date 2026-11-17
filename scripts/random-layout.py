#!/usr/bin/env python3
"""Development layout lab: uv run python scripts/random-layout.py [--seed N]."""
from __future__ import annotations

import argparse
import random
import sys
from collections.abc import Sequence

from brewq import cli

_RANDOM_TERMS = (
    "json", "http", "markdown", "terminal", "pdf", "video",
    "image", "database", "git", "compress", "encrypt", "monitor",
    "search", "diff", "sync", "backup", "proxy", "log", "parser",
    "fuzzy", "render", "stream", "lint", "format", "test",
)
_RANDOM_SORTS = ("trend", "trend", "30d", "365d", "90d", "name")
_RANDOM_LAYOUTS = (
    None,  # default columns
    "name,30d,90d,365d,desc",
    "name,type,ver,bin,desc",
    "name,30d,url",
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, metavar="N",
                        help="Fix the random seed for a reproducible lab run")
    args = parser.parse_args(argv)
    rng = random.Random(args.seed)
    query = rng.choice(_RANDOM_TERMS)
    sort = rng.choice(_RANDOM_SORTS)
    top = rng.randint(4, 10)
    columns = rng.choice(_RANDOM_LAYOUTS)

    command = ["-t", str(top), "-s", sort]
    if columns:
        command.extend(["-c", columns])
    command.append(query)
    print(" ".join(["brewq", *command]), file=sys.stderr)
    return cli.main(command)


if __name__ == "__main__":
    raise SystemExit(main())
