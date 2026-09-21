#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = ROOT / "docs" / "status-dashboard.html"
JSON_PATH = ROOT / "docs" / "status-dashboard-data.json"


def run_json(*args: str) -> object:
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def run_text(*args: str) -> str:
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def short_description(issue: dict) -> str:
    description = " ".join((issue.get("description") or "").split())
    if not description:
        return ""
    if len(description) <= 116:
        return description
    return description[:113].rstrip() + "..."


def lane_names(labels: list[str]) -> list[str]:
    label_set = set(labels)
    lanes = []
    if "stabilization" in label_set:
        lanes.append("Stabilization")
    if "help" in label_set:
        lanes.append("Help and CLI UX")
    if "scripts" in label_set:
        lanes.append("Script-friendly output")
    if "performance" in label_set:
        lanes.append("Performance")
    if "analytics" in label_set:
        lanes.append("Analytics metadata")
    if "docs" in label_set or "readme" in label_set:
        lanes.append("Docs and README")
    if "feedback" in label_set or "research" in label_set:
        lanes.append("Feedback research")
    if "cli" in label_set or "output" in label_set:
        lanes.append("CLI and output")
    return lanes or ["Other"]


def issue_rank(issue: dict) -> tuple[int, str, str]:
    priority = issue.get("priority")
    return (
        priority if priority is not None else 9,
        issue.get("title") or "",
        issue.get("id") or "",
    )


def issue_view(issue: dict) -> dict:
    return {
        "id": issue["id"],
        "title": issue["title"],
        "summary": short_description(issue),
        "labels": issue.get("labels") or [],
        "priority": issue.get("priority"),
    }


def commits() -> list[dict]:
    output = run_text("git", "log", "--oneline", "-8")
    rows = []
    for line in output.splitlines():
        sha, _, subject = line.partition(" ")
        rows.append({"sha": sha, "subject": subject})
    return rows


def build_data() -> dict:
    stats_payload = run_json("bd", "stats", "--json")
    stats = stats_payload["summary"]
    ready = run_json("bd", "ready", "--json")
    active = run_json("bd", "list", "--status=in_progress", "--json")
    closed = stats.get("closed_issues", 0)
    total = stats.get("total_issues", 0)
    completion = round((closed / total) * 100) if total else 0

    workstreams = Counter()
    ready = sorted(ready, key=issue_rank)
    active = sorted(active, key=issue_rank)
    for issue in [*ready, *active]:
        for lane in lane_names(issue.get("labels") or []):
            workstreams[lane] += 1

    signals = [
        {
            "kind": "warn",
            "title": "Release evidence",
            "body": "The stabilization milestone brewq-4oc defines correctness, workflow review, and installed-artifact gates. Issue completion percentage is not release readiness.",
        },
        {
            "kind": "warn",
            "title": "Verification is separate",
            "body": "This dashboard does not run checks. Run uv run python scripts/verify.py and consult issue evidence for results and outstanding release checks.",
        },
    ]

    return {
        "generated_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"),
        "summary_text": "Read-only Homebrew query and analytics. Stabilize state handling and the CLI contract, then review workflows and verify the installed artifact. Beads is the status source.",
        "stats": stats,
        "completion_percent": completion,
        "tests": {
            "passed": None,
            "command": "uv run python scripts/verify.py",
        },
        "ready": [issue_view(issue) for issue in ready],
        "active": [issue_view(issue) for issue in active],
        "workstreams": [
            {"name": name, "count": count}
            for name, count in sorted(workstreams.items(), key=lambda item: (-item[1], item[0]))
        ],
        "commits": commits(),
        "signals": signals,
        "notes": [
            {
                "title": "Product Boundary",
                "body": "Read-only query and analytics. No install, uninstall, upgrade, services, Brewfile, TUI, GUI, or multi-package-manager behavior.",
            },
            {
                "title": "Current Center",
                "body": "Make config, inventory, cache recovery, and output behavior trustworthy before expanding features.",
            },
            {
                "title": "Execution order",
                "body": "Follow bd ready and milestone dependencies: correctness and contract, workflow review, then artifact verification. Design lives in docs/roadmap.md.",
            },
        ],
    }


def update_embedded_data(data: dict) -> None:
    html = HTML_PATH.read_text()
    start_tag = '<script id="dashboard-data" type="application/json">'
    end_tag = "</script>"
    start = html.index(start_tag) + len(start_tag)
    end = html.index(end_tag, start)
    payload = "\n" + json.dumps(data, indent=2) + "\n  "
    HTML_PATH.write_text(html[:start] + payload + html[end:])


def main() -> int:
    data = build_data()
    JSON_PATH.write_text(json.dumps(data, indent=2) + "\n")
    update_embedded_data(data)
    print(f"Updated {JSON_PATH.relative_to(ROOT)} and embedded dashboard data")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
