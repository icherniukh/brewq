#!/usr/bin/env python3
"""Bump the brewq version in pyproject.toml."""

from __future__ import annotations

import re
import subprocess
from argparse import ArgumentParser
from pathlib import Path


def _read(path: Path) -> str:
    return path.read_text()


def _write(path: Path, content: str) -> None:
    path.write_text(content)


def _current(path: Path) -> tuple[int, int, int]:
    text = _read(path)
    m = re.search(r'^version\s*=\s*"(\d+)\.(\d+)\.(\d+)"', text, re.MULTILINE)
    if not m:
        raise SystemExit(f"No version found in {path}")
    return int(m[1]), int(m[2]), int(m[3])


def _replace(path: Path, old: str, new: str) -> None:
    text = _read(path)
    _write(path, text.replace(f'version = "{old}"', f'version = "{new}"', 1))


def main() -> int:
    parser = ArgumentParser(description="Bump the brewq version.")
    parser.add_argument("part", choices=["major", "minor", "patch"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--commit", action="store_true",
                        help="git commit with chore(bump) message")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    path = root / "pyproject.toml"

    major, minor, patch = _current(path)
    if args.part == "major":
        major += 1
        minor = 0
        patch = 0
    elif args.part == "minor":
        minor += 1
        patch = 0
    else:
        patch += 1

    old = f"{_current(path)[0]}.{_current(path)[1]}.{_current(path)[2]}"
    new = f"{major}.{minor}.{patch}"

    if args.dry_run:
        print(f"{old} -> {new} (dry run)")
        return 0

    _replace(path, old, new)
    print(f"{old} -> {new}")

    if args.commit:
        subprocess.run(
            ["git", "add", str(path)],
            cwd=root, check=True,
        )
        subprocess.run(
            ["git", "commit", "-F", "-"],
            input=f"chore(bump): {old} -> {new}\n\nCo-authored-by: CommandCodeBot <noreply@commandcode.ai>\n",
            text=True, cwd=root, check=True,
        )
        print("committed")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
