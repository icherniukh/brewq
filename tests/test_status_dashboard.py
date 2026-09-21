from __future__ import annotations

import importlib.util
from pathlib import Path


def _module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "update-status-dashboard.py"
    spec = importlib.util.spec_from_file_location("status_dashboard", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dashboard_priority_wins_over_old_help_lane():
    dashboard = _module()
    issues = [
        {"id": "help", "priority": 3, "labels": ["help"]},
        {"id": "unknown", "priority": None},
        {"id": "release", "priority": 1},
        {"id": "emergency", "priority": 0},
    ]
    assert [item["id"] for item in sorted(issues, key=dashboard.issue_rank)] == [
        "emergency", "release", "help", "unknown",
    ]


def test_dashboard_does_not_invent_verification_results(monkeypatch):
    dashboard = _module()
    responses = {
        ("bd", "stats", "--json"): {"summary": {"total_issues": 2, "closed_issues": 1}},
        ("bd", "ready", "--json"): [],
        ("bd", "list", "--status=in_progress", "--json"): [],
    }
    monkeypatch.setattr(dashboard, "run_json", lambda *args: responses[args])
    monkeypatch.setattr(dashboard, "commits", lambda: [])
    data = dashboard.build_data()
    assert data["tests"]["passed"] is None
    assert data["completion_percent"] == 50
    assert any("not release readiness" in signal["body"] for signal in data["signals"])
