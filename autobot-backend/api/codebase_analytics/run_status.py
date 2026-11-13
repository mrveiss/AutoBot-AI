# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Durable terminal status for indexing runs, and the "last completed run" pointer (#21003).

A run that was killed (exit -9) keeps the findings it had already stored, and
those were shown afterwards as if they were the whole result.  Task records
live in Redis for a day, so nothing durable said the run never finished.

One record per source lives in the same ChromaDB collection as the findings,
which is the system of record for ``codebase_analytics``
(``autobot_shared.store_authority``):

* ``latest_*``         -- the newest run and how it ended;
* ``last_completed_*`` -- the pointer only a ``completed`` finish advances.

The record names its source under ``owner_source``, never ``source_id``: every
per-source reindex starts by deleting ``where={"source_id": ...}``
(``chromadb_storage._delete_source_documents``), and a record that matched
would be deleted by the very next run together with its pointer.  A reindex
with no source drops the whole collection, record included; no findings are
left for the record to describe in that case.

A failed, killed or cancelled run never moves the pointer.  Its findings stay
stored and are served marked partial (:func:`run_response_fields`).  Nothing
here deletes or rewrites findings.

``abandoned`` is never stored.  A record still ``running`` long after the hard
timeout is *presented* as ``abandoned`` when read (:func:`describe_run_state`);
a read does not write.

Terminal precedence (:func:`record_run_finished`).  A report names a run id and
meets a record whose newest run is the same id, or another one:

=========================  ==================  ===================================
record's newest run        report's run id     outcome
=========================  ==================  ===================================
``running``                the same            applied
terminal                   the same            ignored: the first terminal status
                                               of a run is final
``running``                another             ignored: a run that is still going
                                               owns the record
``running``, overdue       another, unseen     takes over: the record would be
                                               presented as ``abandoned``
                                               (:func:`_is_overdue`), so the run
                                               holding it is gone
``running``, overdue       another, seen       ignored: an older run reporting late
terminal                   another, unseen     takes over: a terminal run sends no
                                               more reports, so an id the record
                                               never saw is a newer run whose
                                               start write was lost
terminal                   another, seen       ignored: an older run reporting late
none                       any                 applied
=========================  ==================  ===================================

"Seen" means the id is in the record's ``seen_run_ids``: the last
``MAX_SEEN_RUN_IDS`` ids, newest last, added by :func:`record_run_started` and by
an accepted take-over.  Run ids are uuid4s with no order, so this list is what
tells a late report of an older run (always listed) from a newer run whose start
was lost (never listed).  An overdue ``running`` record is read as terminal for this
purpose: leaving it in place would drop the newer run's result and keep the source
partial until the next start.  Residual limits: an older run whose start write was
*also* lost is indistinguishable from a newer one and takes over; and ids older
than the cap are forgotten, so a report that late is read as unseen.  A record
written before the field existed reads as an empty list.
"""

import asyncio
import functools
import inspect
import json
import signal
from datetime import datetime, timedelta, timezone

from fastapi.responses import JSONResponse, PlainTextResponse

from api.source_scope import require_source_id
from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.store_authority import system_of_record
from autobot_shared.time_utils import parse_utc_iso

from .indexing_executor import _SUBPROCESS_HARD_TIMEOUT
from .storage import get_code_collection_async

logger = get_logger(__name__)

SYSTEM_OF_RECORD = system_of_record("codebase_analytics")

STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_KILLED = "killed"
STATUS_ABANDONED = "abandoned"
STATUS_CANCELLED = "cancelled"

#: A run in one of these states is over and its status is final.
TERMINAL_STATUSES = frozenset({STATUS_COMPLETED, STATUS_FAILED, STATUS_KILLED, STATUS_CANCELLED})
#: Results from a run in one of these states are partial.
PARTIAL_STATUSES = frozenset({STATUS_FAILED, STATUS_KILLED, STATUS_ABANDONED, STATUS_CANCELLED, STATUS_RUNNING})

_DEFAULT_ABANDON_GRACE_SECONDS = 300
#: Slack past the hard timeout before a still-``running`` record is presented as abandoned.
ABANDON_GRACE_SECONDS = env_int_clamped(
    "AUTOBOT_INDEXING_ABANDON_GRACE_SECONDS", _DEFAULT_ABANDON_GRACE_SECONDS, 30, 86400
)

#: Structural bound on the run ids a record remembers (see the module docstring).
MAX_SEEN_RUN_IDS = 8
_SEEN_KEY = "seen_run_ids"
_RECORD_TYPE = "run_status"
_OWNER_KEY = "owner_source"
#: Serialises read-modify-write inside one process.  Two processes (the worker and
#: its supervisor) can still interleave; terminal precedence is what keeps that safe.
_UPDATE_LOCK = asyncio.Lock()


class RunKilled(RuntimeError):
    """The run's worker was killed (SIGKILL: the watchdog, a time limit or the OOM killer)."""


def watchdog_kill_reason(idle_seconds: int, limit_seconds: int) -> str:
    """Reason recorded when the progress watchdog killed the worker."""
    return f"killed by the progress watchdog: no progress for {idle_seconds}s (limit {limit_seconds}s)"


def hard_timeout_kill_reason(limit_seconds: int) -> str:
    """Reason recorded when the hard timeout killed the worker."""
    return f"killed by the hard timeout: run exceeded {limit_seconds}s"


def run_record_id(source_id: str | None) -> str:
    """Document id of the run record for ``source_id`` (a source is required)."""
    return f"codebase_run_{require_source_id(source_id, 'run record id')}"


def status_for_returncode(returncode: int) -> str:
    """Map a subprocess exit code to a terminal status: SIGKILL is ``killed``, anything else ``failed``."""
    return STATUS_KILLED if returncode == -int(signal.SIGKILL) else STATUS_FAILED


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _as_utc(moment: datetime) -> datetime:
    """*moment* as an aware datetime: a naive one is read as UTC, the convention of ``parse_utc_iso``."""
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment


async def _read(collection, source_id: str) -> dict:
    result = await collection.get(ids=[run_record_id(source_id)], include=["metadatas"])
    metas = (result or {}).get("metadatas") or []
    return dict(metas[0]) if metas else {}


async def _write(collection, source_id: str, meta: dict) -> None:
    meta = {**meta, "type": _RECORD_TYPE, _OWNER_KEY: source_id}
    document = f"Run status {meta.get('latest_status', '')} for {source_id}"
    await collection.upsert(ids=[run_record_id(source_id)], documents=[document], metadatas=[meta])


async def _update(source_id: str | None, change) -> bool:
    """Apply ``change(old_record) -> new_record | None``; True only if a record was written.

    A run with no source (the dev ``root_path`` mode) has no record: there is no
    source for a reader to ask about.
    """
    if not source_id:
        return False
    collection = await get_code_collection_async()
    if collection is None:
        logger.warning("Run status not recorded for %s: code collection unavailable (#21003)", source_id)
        return False
    try:
        async with _UPDATE_LOCK:
            new = change(await _read(collection, source_id))
            if new is not None:
                await _write(collection, source_id, new)
        return new is not None
    except Exception as exc:
        logger.warning("Run status not recorded for %s (#21003): %s", source_id, exc)
        return False


def _decode_seen(meta: dict) -> list[str]:
    """The run ids a record has seen; a record without the field (or with a damaged one) has none."""
    try:
        ids = json.loads(meta.get(_SEEN_KEY) or "[]")
    except (TypeError, ValueError):
        return []
    return [i for i in ids if isinstance(i, str)] if isinstance(ids, list) else []


def _encode_seen(ids: list[str]) -> str:
    """Chroma metadata is scalar, so the bounded list travels as a JSON string."""
    return json.dumps(ids[-MAX_SEEN_RUN_IDS:])


def _with_seen(meta: dict, run_id: str) -> str:
    return _encode_seen([i for i in _decode_seen(meta) if i != run_id] + [run_id])


async def record_run_started(source_id: str | None, run_id: str) -> bool:
    """Record ``run_id`` as the newest run, ``running``.  A new run id always starts fresh.

    Whatever the previous run's status, it is replaced; the completed pointer is kept.
    """
    return await _update(
        source_id,
        lambda old: {
            **old,
            "latest_run_id": run_id,
            _SEEN_KEY: _with_seen(old, run_id),
            "latest_status": STATUS_RUNNING,
            "latest_reason": "",
            "latest_started_at": _now().isoformat(),
            "latest_finished_at": "",
        },
    )


def _finish(old: dict, run_id: str, status: str, reason: str) -> dict | None:
    """The record after ``run_id`` ended as ``status``, or ``None`` to leave ``old`` as it is.

    See the outcome table in the module docstring.
    """
    newest, newest_status = old.get("latest_run_id"), old.get("latest_status")
    if newest == run_id and newest_status in TERMINAL_STATUSES:
        return None  # the first terminal status of a run is final
    still_going = newest_status == STATUS_RUNNING and not _is_overdue(old, _SUBPROCESS_HARD_TIMEOUT, _now())
    if newest and newest != run_id and still_going:
        logger.warning("Run %s report (%s) ignored: run %s is still running", run_id, status, newest)
        return None
    if newest and newest != run_id and run_id in _decode_seen(old):
        logger.warning("Run %s report (%s) ignored: it is older than run %s", run_id, status, newest)
        return None
    finished = _now().isoformat()
    new = {**old, "latest_run_id": run_id, "latest_status": status, "latest_reason": reason}
    new["latest_finished_at"] = finished
    new[_SEEN_KEY] = _with_seen(old, run_id)
    if newest != run_id:
        new["latest_started_at"] = ""  # its start was never recorded
    if status == STATUS_COMPLETED:
        new["last_completed_run_id"] = run_id
        new["last_completed_at"] = finished
    return new


async def record_run_finished(source_id: str | None, run_id: str, status: str, reason: str = "") -> bool:
    """Record how ``run_id`` ended.  Only ``completed`` advances the last-completed pointer.

    The first terminal status of a run is final: a supervisor reporting a crash
    after the worker wrote ``completed`` (or the reverse) changes nothing.  True
    if the record was written.
    """
    if status not in TERMINAL_STATUSES:
        raise ValueError(f"not a terminal run status: {status!r}")
    return await _update(source_id, lambda old: _finish(old, run_id, status, reason))


def _is_overdue(meta: dict, hard_timeout: float, now: datetime) -> bool:
    """Whether a ``running`` record began longer ago than the hard timeout plus the abandon grace."""
    started = meta.get("latest_started_at")
    if meta.get("latest_status") != STATUS_RUNNING or not started:
        return False
    try:
        begun = parse_utc_iso(started)  # a naive timestamp is read as UTC
    except (ValueError, TypeError):
        return False
    return now - begun > timedelta(seconds=hard_timeout + ABANDON_GRACE_SECONDS)


def _present(meta: dict, hard_timeout: float, now: datetime) -> dict:
    """The record as readers see it.  A run still ``running`` past its limit reads as ``abandoned``."""
    status, reason, finished = (
        meta.get("latest_status", ""),
        meta.get("latest_reason", ""),
        meta.get("latest_finished_at", ""),
    )
    if _is_overdue(meta, hard_timeout, now):
        status, reason, finished = STATUS_ABANDONED, "no completion reported within the limit", ""
    return {
        "run_id": meta.get("latest_run_id", ""),
        "status": status,
        "partial": status in PARTIAL_STATUSES,
        "reason": reason,
        "started_at": meta.get("latest_started_at", ""),
        "finished_at": finished,
        "last_completed_at": meta.get("last_completed_at", ""),
    }


async def describe_run_state(
    source_id: str | None,
    hard_timeout: float = _SUBPROCESS_HARD_TIMEOUT,
    now: datetime | None = None,
    strict: bool = False,
) -> dict | None:
    """The newest run's state, or ``None`` when no run was ever recorded for the source.

    One read, no write.  ``partial`` is true when the newest run did not
    complete, i.e. the findings in storage may come from an interrupted run.
    ``last_completed_at`` is when the last complete run finished (empty if none
    ever did).  A naive ``now`` is read as UTC.  ``strict`` raises when the
    collection cannot be opened, where the default reads that as "no run".
    """
    if not source_id:
        return None
    collection = await get_code_collection_async()
    if collection is None:
        if strict:
            raise RuntimeError("code collection unavailable")
        return None
    meta = await _read(collection, source_id)
    return _present(meta, hard_timeout, _as_utc(now) if now else _now()) if meta else None


async def run_response_fields(source_id: str | None) -> dict:
    """``{"partial": bool, "run": dict | None}`` -- the ONE shape every results route carries.

    A source with no run record (indexed before run records existed, or never
    indexed) is ``run: None, partial: False``: nothing says its results are
    incomplete, so none is claimed.  A record that cannot be read is reported
    the same way and logged; it must not fail the findings it only labels.
    The run-state route, which serves nothing else, reads strictly instead.
    """
    try:
        run = await describe_run_state(source_id)
    except Exception as exc:
        logger.warning("Run state unreadable for %s (#21003): %s", source_id, exc)
        run = None
    return run_fields(run)


def run_fields(run: dict | None) -> dict:
    """The ``partial``/``run`` pair for a run state already read (``None``: no run record)."""
    return {"partial": bool(run and run["partial"]), "run": run}


def with_run_state(handler):
    """Route decorator: add ``partial`` and ``run`` to a handler that returns its body as a ``dict``.

    The fields are merged into the dict and the response is built once, so a large
    body is encoded once.  Anything else the handler returns (an error response, a
    redirect, a download) is passed through untouched, ``background`` included.
    The handler must receive ``source_id`` (by name or by position).

    The run state is read BEFORE the handler reads the findings.  This closes one
    race: a run records ``completed`` only after its last write, so when a run
    completes between the two reads the body says ``partial`` (read afterwards, it
    would label findings from before the last writes as complete).  One window
    remains: a reindex that STARTS between the two reads deletes the source's
    findings first, so the handler can read thin findings under the previous
    run's ``completed``.  The next request reads ``running`` and is labelled.
    """
    signature = inspect.signature(handler)

    @functools.wraps(handler)
    async def wrapper(*args, **kwargs):
        source_id = signature.bind_partial(*args, **kwargs).arguments.get("source_id")
        fields = await run_response_fields(source_id)
        result = await handler(*args, **kwargs)
        if not isinstance(result, dict):
            return result
        return JSONResponse({**result, **fields})

    wrapper.labels_run_state = True  # functools.wraps in the outer decorators carries it to the route
    return wrapper


def partial_report_banner(run: dict | None) -> str:
    """Markdown banner for a report built from a non-completed run; empty otherwise."""
    if not run or not run["partial"]:
        return ""
    since = run["last_completed_at"] or "never"
    return (
        f"> **Partial results.** The newest indexing run did not complete (status: {run['status']}). "
        f"These findings may come from the interrupted run. Last completed run: {since}.\n\n"
    )


def report_response(report: str, fields: dict, source_id: str) -> PlainTextResponse:
    """The markdown report download, labelled partial when its run did not complete."""
    run = fields["run"]
    headers = {
        "Content-Disposition": 'attachment; filename="code-analysis-report.md"',
        "X-Source-Id": source_id,
        "X-Run-Partial": str(fields["partial"]).lower(),
    }
    if run:
        headers["X-Run-Status"] = run["status"]
        headers["X-Run-Last-Completed-At"] = run["last_completed_at"]
    return PlainTextResponse(
        content=partial_report_banner(run) + report,
        media_type="text/markdown; charset=utf-8",
        headers=headers,
    )
