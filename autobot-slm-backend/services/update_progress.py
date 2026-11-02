# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""What a running self-update is doing, read from its own log (#20254).

Once the SLM restarts, the in-memory job is gone and the page has nothing to show, so a healthy run of
30 minutes looks hung. The detached run keeps writing its log; this reports that log's position. Task and
play names are redacted, and the route serving this is admin-only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autobot_shared.env_utils import env_int_clamped
from services.self_update_log_reader import read_self_update_verdict
from services.update_report import _safe

#: A live run whose log has not moved for this long is reported as quiet. Not a failure: pip can be silent.
STALL_SECONDS = env_int_clamped("SLM_UPDATE_PROGRESS_STALL_SECONDS", 600, min_v=30)


def _state(complete: bool, run_active: bool | None, quiet_seconds: float | None) -> str:
    if complete:
        return "finished"
    if run_active is False:
        return "exited_without_recap"
    if run_active is None:
        return "unknown"
    return "quiet" if quiet_seconds is not None and quiet_seconds > STALL_SECONDS else "running"


def _seconds_since(moment: datetime | None, now: datetime) -> float | None:
    return max((now - moment).total_seconds(), 0.0) if moment else None


def _log_mtime(log_path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(log_path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def _parse(stamp: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(stamp) if stamp else None
    except ValueError:
        return None


def build_update_progress(
    log_path: Path, run_active: bool | None, since: str | None = None, now: datetime | None = None
) -> dict[str, Any]:
    """The run at or after *since*: its play, task, last log line and state. Blocking: reads the log."""
    now = now or datetime.now(timezone.utc)
    verdict = read_self_update_verdict(log_path, not_before=since)
    if not verdict.log_present or verdict.from_rotated_log:
        return {"state": "waiting", "play": None, "task": None, "last_line_at": None, "elapsed_seconds": None}
    last_line = _log_mtime(log_path)
    return {
        "state": _state(verdict.complete, run_active, _seconds_since(last_line, now)),
        "play": _safe(verdict.plays_seen[-1]) if verdict.plays_seen else None,
        "task": _safe(verdict.last_task) if verdict.last_task else None,
        "last_line_at": last_line.isoformat() if last_line else None,
        "elapsed_seconds": _seconds_since(_parse(verdict.run_started_at), now),
    }
