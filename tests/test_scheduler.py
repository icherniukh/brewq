from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from brewq import cache, scheduler


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("BREWQ_CACHE_DIR", str(tmp_path))


def _load(source: str = "seed", age: float = 0) -> cache.CacheLoad:
    return cache.CacheLoad(source=source, packages=[], age_seconds=age)


def test_fresh_user_cache_does_not_spawn():
    with patch("brewq.scheduler.subprocess.Popen") as spawn:
        outcome = scheduler.schedule_if_needed(_load("user", age=10), max_age=100)

    assert outcome == "fresh"
    spawn.assert_not_called()


def test_seed_schedules_once_and_repeated_command_sees_pending():
    with patch("brewq.scheduler.subprocess.Popen") as spawn:
        spawn.return_value.pid = 123
        first = scheduler.schedule_if_needed(_load("seed"), max_age=100, now=1_000)
        second = scheduler.schedule_if_needed(_load("seed"), max_age=100, now=1_001)

    assert first == "scheduled"
    assert second == "pending"
    spawn.assert_called_once()
    state = json.loads(scheduler.state_path().read_text())
    assert state["state"] == "scheduled"
    assert state["pid"] == 123


def test_failed_attempt_observes_retry_cooldown():
    scheduler.write_state({"state": "failed", "completed_at": 900, "detail": "offline"})

    with patch("brewq.scheduler.subprocess.Popen") as spawn:
        outcome = scheduler.schedule_if_needed(_load("seed"), max_age=100, now=1_000)

    assert outcome == "cooldown"
    spawn.assert_not_called()


def test_stale_scheduled_state_is_replaced():
    scheduler.write_state({"state": "scheduled", "scheduled_at": 1, "pid": 12})

    with patch("brewq.scheduler.subprocess.Popen") as spawn:
        spawn.return_value.pid = 456
        outcome = scheduler.schedule_if_needed(_load("seed"), max_age=100, now=5_000)

    assert outcome == "scheduled"
    assert scheduler.read_state()["pid"] == 456


def test_worker_waits_then_records_complete():
    scheduler.write_state({"state": "scheduled", "scheduled_at": 1_000, "pid": 123})
    clock = [1_000.0]

    def sleep(seconds: float) -> None:
        clock[0] += seconds

    result = cache.RefreshResult(cache.RefreshOutcome.COMPLETE, cache.cache_path())
    with patch("brewq.scheduler.cache_mod.refresh", return_value=result):
        rc = scheduler.run_worker(
            now=lambda: clock[0],
            sleep=sleep,
            loadavg=lambda: (0.0, 0.0, 0.0),
            cpu_count=lambda: 4,
        )

    assert rc == 0
    assert clock[0] == 1_300
    state = scheduler.read_state()
    assert state["state"] == "complete"
    assert state["completed_at"] == 1_300


def test_worker_defers_after_thirty_minutes_of_high_load():
    scheduler.write_state({"state": "scheduled", "scheduled_at": 1_000, "pid": 123})
    clock = [1_000.0]

    def sleep(seconds: float) -> None:
        clock[0] += seconds

    with patch("brewq.scheduler.cache_mod.refresh") as refresh:
        rc = scheduler.run_worker(
            now=lambda: clock[0],
            sleep=sleep,
            loadavg=lambda: (8.0, 0.0, 0.0),
            cpu_count=lambda: 4,
        )

    assert rc == 0
    refresh.assert_not_called()
    assert clock[0] == 2_800
    assert scheduler.read_state()["state"] == "deferred"


def test_worker_records_partial_and_truncates_detail():
    scheduler.write_state({"state": "scheduled", "scheduled_at": 1_000, "pid": 123})
    result = cache.RefreshResult(
        cache.RefreshOutcome.METADATA_ONLY,
        cache.cache_path(),
        analytics_error="x" * 500,
    )
    with patch("brewq.scheduler.cache_mod.refresh", return_value=result):
        scheduler.run_worker(
            now=lambda: 1_300,
            sleep=lambda _seconds: None,
            loadavg=lambda: (0.0, 0.0, 0.0),
            cpu_count=lambda: 4,
        )

    state = scheduler.read_state()
    assert state["state"] == "partial"
    assert len(state["detail"]) == 300
