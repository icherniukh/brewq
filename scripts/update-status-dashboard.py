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


def issue_rank(issue: dict) -> tuple[int, int, str]:
    labels = set(issue.get("labels") or [])
    title = issue.get("title") or ""
    if "help" in labels:
        lane = 0
    elif "scripts" in labels:
        lane = 1
    elif "preset" in title.lower() or "calibrate" in title.lower():
        lane = 2
    elif "readme" in labels:
        lane = 3
    elif "performance" in labels:
        lane = 4
    elif "feedback" in labels:
        lane = 5
    elif "analytics" in labels:
        lane = 6
    else:
        lane = 7
    return (lane, issue.get("priority") or 9, issue.get("id") or "")


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


def git_status_signal() -> dict:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    status = result.stdout.rstrip()
    if not status:
        return {
            "kind": "good",
            "title": "Working tree clean",
            "body": "No uncommitted files are currently reported by git status.",
        }
    ignored_paths = {
        ".beads/interactions.jsonl",
        "README.md",
        "docs/status-dashboard.html",
        "docs/status-dashboard-data.json",
        "scripts/",
        "scripts/serve-status-dashboard.py",
        "scripts/update-status-dashboard.py",
    }
    lines = status.splitlines()
    meaningful = []
    has_uv_lock = False
    for line in lines:
        path = line[3:]
        if path.endswith("uv.lock"):
            has_uv_lock = True
        elif path not in ignored_paths:
            meaningful.append(line)
    if not meaningful and has_uv_lock:
        return {
            "kind": "warn",
            "title": "Repo hygiene note",
            "body": "uv.lock is untracked and intentionally left out until lockfile policy is decided.",
        }
    if not meaningful:
        return {
            "kind": "good",
            "title": "Dashboard refresh is clean",
            "body": "Only dashboard-generated files changed during this refresh.",
        }
    return {
        "kind": "warn",
        "title": "Working tree has local changes",
        "body": f"{len(meaningful)} non-dashboard git status entries need review before shipping.",
    }


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
            "kind": "good",
            "title": "Recent win: search correctness",
            "body": "Tapped formulae are included from live Homebrew search, and loose fuzzy formula matches no longer surface misleading results.",
        },
        {
            "kind": "warn",
            "title": "Open decision: user-facing output",
            "body": "Help shape, script-friendly mode, column presets, and color meaning need to lock before the README should become public-facing.",
        },
        {
            "kind": "warn",
            "title": "Freshness caveat",
            "body": "Tracker and git data refresh live; test count is a recorded verification value, not rerun by the dashboard refresh.",
        },
        git_status_signal(),
    ]

    return {
        "generated_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"),
        "summary_text": "Read-only Homebrew query and analytics tool. Current work is focused on output polish, metadata signals, performance visibility, script-friendly behavior, and a stronger public README.",
        "stats": stats,
        "completion_percent": completion,
        "tests": {
            "passed": 85,
            "command": "PYTHONPATH=src uv run pytest",
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
                "body": "Make terminal output trustworthy, compact, explainable, and script-friendly before expanding optional analytics columns.",
            },
            {
                "title": "Next Best Move",
                "body": "Lock column presets and help text, then turn the README into a public first impression with real output capture.",
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
