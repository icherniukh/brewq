#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time
from pathlib import Path

from brewq import analytics, brew, seed


def _sanitize(data: dict) -> None:
    for formula in data.get("formulae", []):
        formula["installed"] = []
    for cask in data.get("casks", []):
        cask["installed"] = None


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the bundled brewq cache seed.")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    data = brew.info_all()
    analytics.merge_into_brew_data(data, analytics.fetch_all())
    _sanitize(data)
    generated_at = int(time.time())
    payload = seed.encode(data, generated_at=generated_at)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print(
        f"seed: {len(data['formulae'])} formulae, {len(data['casks'])} casks; "
        f"generated {generated_at}; {len(payload)} bytes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
