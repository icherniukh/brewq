from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from brewq import cache as cache_mod
from brewq import config as config_mod

INITIAL_DELAY = 300
LOAD_RETRY_DELAY = 300
MAX_DEFERRAL = 1800
RETRY_COOLDOWN = 3600
LOAD_LIMIT = 0.75
_STATE_FILE = "refresh-state.json"
_LOCK_FILE = "schedule.lock"
_ACTIVE_STALE_AFTER = 3600


def state_path() -> Path:
    return config_mod.cache_dir() / _STATE_FILE


def lock_path() -> Path:
    return config_mod.cache_dir() / _LOCK_FILE


def read_state() -> dict[str, Any]:
    try:
        data = json.loads(state_path().read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_state(state: dict[str, Any]) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        tmp = Path(handle.name)
        try:
            json.dump(state, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    try:
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _state_time(state: dict[str, Any]) -> float:
    for key in ("completed_at", "started_at", "scheduled_at"):
        try:
            return float(state[key])
        except (KeyError, TypeError, ValueError):
            continue
    return 0.0


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _schedule_decision(state: dict[str, Any], now: float) -> str | None:
    name = state.get("state")
    age = max(0.0, now - _state_time(state))
    if name in {"scheduled", "running"} and age <= _ACTIVE_STALE_AFTER:
        pid = state.get("pid")
        if pid and not _pid_alive(pid):
            return None
        return "pending"
    if name in {"partial", "deferred", "failed"} and age < RETRY_COOLDOWN:
        return "cooldown"
    return None


def schedule_if_needed(
    load: cache_mod.CacheLoad,
    max_age: int,
    *,
    now: float | None = None,
) -> str:
    if not config_mod.auto_refresh_enabled(config_mod.load()):
        return "disabled"
    current_time = time.time() if now is None else now
    if not load.requires_refresh and load.source == "user" and load.age_seconds < max_age:
        return "fresh"

    path = lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as lock_fh:
        try:
            fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return "pending"
        decision = _schedule_decision(read_state(), current_time)
        if decision is not None:
            return decision
        process = subprocess.Popen(
            [sys.executable, "-m", "brewq.scheduler"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
        write_state({
            "state": "scheduled",
            "scheduled_at": current_time,
            "pid": process.pid,
        })
    return "scheduled"


def _detail(value: object) -> str:
    return " ".join(str(value).splitlines())[:300]


def _record_result(result: cache_mod.RefreshResult, completed_at: float) -> None:
    if result.outcome in {cache_mod.RefreshOutcome.COMPLETE, cache_mod.RefreshOutcome.FRESH}:
        write_state({"state": "complete", "completed_at": completed_at})
    elif result.outcome is cache_mod.RefreshOutcome.METADATA_ONLY:
        write_state({
            "state": "partial",
            "completed_at": completed_at,
            "detail": _detail(result.analytics_error or "analytics unavailable"),
        })
    else:
        write_state({
            "state": "deferred",
            "completed_at": completed_at,
            "detail": "another refresh owns the cache lock",
        })


def run_worker(
    *,
    now: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
    loadavg: Callable[[], tuple[float, float, float]] = os.getloadavg,
    cpu_count: Callable[[], int | None] = os.cpu_count,
) -> int:
    path = lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as lock_fh:
        fcntl.flock(lock_fh, fcntl.LOCK_EX)
        state = read_state()
        scheduled_at = float(state.get("scheduled_at", now()))
        due_at = scheduled_at + INITIAL_DELAY
        sleep(max(0.0, due_at - now()))

        try:
            os.nice(10)
        except OSError:
            pass

        while loadavg()[0] / max(cpu_count() or 1, 1) > LOAD_LIMIT:
            if now() - scheduled_at >= MAX_DEFERRAL:
                write_state({
                    "state": "deferred",
                    "completed_at": now(),
                    "detail": "system remained busy",
                })
                return 0
            sleep(LOAD_RETRY_DELAY)

        write_state({"state": "running", "started_at": now(), "pid": os.getpid()})
        try:
            result = cache_mod.refresh(force=True)
        except Exception as exc:
            write_state({
                "state": "failed",
                "completed_at": now(),
                "detail": _detail(exc),
            })
            return 1
        _record_result(result, now())
        return 0


def main() -> int:
    return run_worker()


if __name__ == "__main__":
    raise SystemExit(main())
