#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

from brewq import analytics, brew, seed


def _sanitize(data: dict) -> None:
    """Remove builder-local paths and installed state from public seed metadata."""
    home = str(Path.home()).rstrip("/")
    # Match a path token, not a similar account or a path inside another tree.
    pattern = re.compile(
        r'''(?P<boundary>^|[\s"'(<=>])''' + re.escape(home) + r'''(?=$|/|[\s"'`,;:)\]}>])'''
    ) if home else None

    def redact(value):
        if isinstance(value, str):
            return pattern.sub(r"\g<boundary>~", value) if pattern else value
        if isinstance(value, list):
            return [redact(item) for item in value]
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                clean_key = redact(key)
                if clean_key in result:
                    raise ValueError("seed home-path redaction causes a dictionary key collision")
                result[clean_key] = redact(item)
            return result
        return value

    clean = redact(data)
    data.clear()
    data.update(clean)
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
