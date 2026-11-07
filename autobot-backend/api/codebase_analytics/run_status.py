# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Durable terminal status for indexing runs, and the "latest complete run" pointer (#21003).

A run that was killed (exit -9) keeps the findings it had already stored, and
those were shown afterwards as if they were the whole result.  Task records
live in Redis for a day, so nothing durable said the run never finished.

One record per source lives next to the findings, in the same ChromaDB
collection (the system of record for ``codebase_analytics``, see
``autobot_shared.store_authority``):

* ``latest_*``         -- the newest run and how it ended;
* ``last_completed_*`` -- the pointer only a ``completed`` finish advances.

A failed, killed or abandoned run never moves the pointer.  Its findings stay
stored and are reported as partial through :func:`describe_run_state`.  Nothing
here deletes data.
"""

import signal
from datetime import datetime, timedelta, timezone

from autobot_shared.logging_manager import get_logger

from .storage import get_code_collection_async

logger = get_logger(__name__)

STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_KILLED = "killed"
STATUS_ABANDONED = "abandoned"
STATUS_CANCELLED = "cancelled"

#: A run in one of these states is over; the supervisor and the watchdog stop on them.
TERMINAL_STATUSES = frozenset({STATUS_COMPLETED, STATUS_FAILED, STATUS_KILLED, STATUS_CANCELLED})
#: Results from a run in one of these states are partial.
PARTIAL_STATUSES = frozenset({STATUS_FAILED, STATUS_KILLED, STATUS_ABANDONED, STATUS_CANCELLED, STATUS_RUNNING})

#: Slack past the hard timeout before a still-``running`` record counts as abandoned.
ABANDON_GRACE_SECONDS = 300

_RECORD_TYPE = "run_status"
_DEFAULT_SOURCE = "default"


class RunKilled(RuntimeError):
    """The run's worker was killed (SIGKILL: the watchdog, a time limit or the OOM killer)."""


def run_record_id(source_id: str | None) -> str:
    """Document id of the run record for ``source_id``."""
    return f"codebase_run_{source_id or _DEFAULT_SOURCE}"


def status_for_returncode(returncode: int) -> str:
    """Map a subprocess exit code to a terminal status: SIGKILL is ``killed``, anything else ``failed``."""
    return STATUS_KILLED if returncode == -int(signal.SIGKILL) else STATUS_FAILED


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


async def _read(collection, source_id: str | None) -> dict:
    result = await collection.get(ids=[run_record_id(source_id)], include=["metadatas"])
    metas = (result or {}).get("metadatas") or []
    return dict(metas[0]) if metas else {}


async def _write(collection, source_id: str | None, meta: dict) -> None:
    meta = {**meta, "type": _RECORD_TYPE, "source_id": source_id or _DEFAULT_SOURCE}
    document = f"Run status {meta.get('latest_status', '')} for {meta['source_id']}"
    await collection.upsert(ids=[run_record_id(source_id)], documents=[document], metadatas=[meta])


async def record_run_started(source_id: str | None, run_id: str) -> bool:
    """Record ``run_id`` as the newest run, ``running``.  Leaves the completed pointer alone."""
    return await _update(
        source_id,
        lambda old: {
            **old,
            "latest_run_id": run_id,
            "latest_status": STATUS_RUNNING,
            "latest_reason": "",
            "latest_started_at": _now().isoformat(),
            "latest_finished_at": "",
        },
    )


async def record_run_finished(source_id: str | None, run_id: str, status: str, reason: str = "") -> bool:
    """Record how ``run_id`` ended.  Only ``completed`` advances the last-completed pointer.

    A run that already holds a terminal status keeps it: a supervisor reporting
    a crash after the worker wrote ``completed`` must not overwrite it.
    """
    if status not in TERMINAL_STATUSES and status != STATUS_ABANDONED:
        raise ValueError(f"not a terminal run status: {status!r}")

    def apply(old: dict) -> dict | None:
        same_run = old.get("latest_run_id") == run_id
        if same_run and old.get("latest_status") in TERMINAL_STATUSES:
            return None
        if not same_run and status != STATUS_COMPLETED and old.get("latest_run_id"):
            return None  # a newer run owns the record; this one's failure is not its status
        finished = _now().isoformat()
        new = {
            **old,
            "latest_run_id": run_id,
            "latest_status": status,
            "latest_reason": reason,
            "latest_finished_at": finished,
        }
        if status == STATUS_COMPLETED:
            new["last_completed_run_id"] = run_id
            new["last_completed_at"] = finished
        return new

    return await _update(source_id, apply)


async def _update(source_id: str | None, change) -> bool:
    collection = await get_code_collection_async()
    if collection is None:
        logger.warning("Run status not recorded for %s: code collection unavailable (#21003)", source_id)
        return False
    try:
        new = change(await _read(collection, source_id))
        if new is not None:
            await _write(collection, source_id, new)
        return True
    except Exception as exc:
        logger.warning("Run status not recorded for %s (#21003): %s", source_id, exc)
        return False


def _is_overdue(meta: dict, hard_timeout: int, now: datetime) -> bool:
    started = meta.get("latest_started_at")
    if meta.get("latest_status") != STATUS_RUNNING or not started:
        return False
    try:
        begun = datetime.fromisoformat(started)
    except ValueError:
        return False
    return now - begun > timedelta(seconds=hard_timeout + ABANDON_GRACE_SECONDS)


async def sweep_abandoned(source_id: str | None, hard_timeout: int, now: datetime | None = None) -> bool:
    """Mark a run left ``running`` past its hard timeout as ``abandoned``.  True if it did.

    Called on read, so a worker that died without any exit path (host restart,
    OOM of the supervisor itself) is reported instead of shown as in progress.
    """
    moment = now or _now()
    changed = []

    def apply(old: dict) -> dict | None:
        if not _is_overdue(old, hard_timeout, moment):
            return None
        changed.append(old["latest_run_id"])
        return {
            **old,
            "latest_status": STATUS_ABANDONED,
            "latest_reason": f"still running {hard_timeout}s after start; the worker is gone",
            "latest_finished_at": moment.isoformat(),
        }

    await _update(source_id, apply)
    if changed:
        logger.warning("Run %s for %s marked abandoned (#21003)", changed[0], source_id)
    return bool(changed)


async def describe_run_state(source_id: str | None, hard_timeout: int) -> dict | None:
    """What a reader needs to label results: ``None`` when no run was ever recorded.

    ``partial`` is true when the newest run did not complete, i.e. the findings
    in storage may come from an interrupted run.  ``last_completed_*`` names the
    run whose result is the latest complete one (empty if none ever finished).
    """
    await sweep_abandoned(source_id, hard_timeout)
    collection = await get_code_collection_async()
    if collection is None:
        return None
    meta = await _read(collection, source_id)
    if not meta:
        return None
    status = meta.get("latest_status", "")
    return {
        "latest_run_id": meta.get("latest_run_id", ""),
        "status": status,
        "partial": status in PARTIAL_STATUSES,
        "reason": meta.get("latest_reason", ""),
        "finished_at": meta.get("latest_finished_at", ""),
        "last_completed_run_id": meta.get("last_completed_run_id", ""),
        "last_completed_at": meta.get("last_completed_at", ""),
    }
