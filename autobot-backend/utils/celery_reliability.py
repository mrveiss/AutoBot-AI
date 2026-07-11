# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Celery reliability helpers: idempotency guard, retry policy, dead-letter parking (#11586).

Celery delivers at-least-once: with the 12 h broker visibility timeout set in
``celery_app.py``, a worker crash (or visibility-timeout overrun) mid-task
causes broker redelivery and the task body runs twice.  ``idempotent_task``
claims ``celery:dedup:{task_id}`` with ``SET NX`` before the body executes so
a redelivered duplicate becomes a logged no-op.

``DeadLetterTask`` parks terminally failed tasks (retries exhausted or a
non-retryable error) in a bounded Redis list so failures stay queryable via
``GET /api/health/celery-dead-letter`` instead of vanishing when the Celery
result TTL expires.

``CELERY_TRANSIENT_ERRORS`` mirrors the canonical retryable vs non-retryable
exception split in ``autobot_shared/retry_mechanism.py`` (#7010):
ConnectionError/TimeoutError/OSError back off with jitter; validation errors
(ValueError/TypeError) fail fast and are never retried.
"""

import json
import logging
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Dict

from celery import Task

from autobot_shared.redis_client import get_async_redis_client, get_redis_client
from autobot_shared.ssot_config import config
from autobot_shared.status_enums import TaskStatus

logger = logging.getLogger(__name__)

# Transient errors that trigger Celery autoretry — the retryable set from
# autobot_shared/retry_mechanism.py (#7010). ValueError/TypeError are
# intentionally absent so validation failures fail fast without retry.
CELERY_TRANSIENT_ERRORS = (ConnectionError, TimeoutError, OSError)

DEDUP_KEY_PREFIX = "celery:dedup:"
DEAD_LETTER_KEY = "celery:dead_letter"
_REDIS_DATABASE = "main"
_ARGS_SUMMARY_MAX_CHARS = 400


def _resolve_positive_int(field_name: str, env_var: str, default: int) -> int:
    """Return a positive int from ``config.misc.<field_name>``, else *default*."""
    try:
        raw = getattr(config.misc, field_name)
    except Exception:  # config unavailable (e.g. stubbed in tests)
        return default
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning("%s=%r is not an integer; falling back to %d", env_var, raw, default)
        return default
    if value <= 0:
        logger.warning("%s=%d must be positive; falling back to %d", env_var, value, default)
        return default
    return value


# Dedup claims must outlive the broker visibility timeout (43200 s default in
# celery_app.py), otherwise a redelivery after claim expiry re-executes the task.
CELERY_DEDUP_TTL = _resolve_positive_int("celery_dedup_ttl", "AUTOBOT_CELERY_DEDUP_TTL", 43200)
CELERY_MAX_RETRIES = _resolve_positive_int("celery_max_retries", "AUTOBOT_CELERY_MAX_RETRIES", 3)
CELERY_RETRY_BACKOFF_MAX = _resolve_positive_int("celery_retry_backoff_max", "AUTOBOT_CELERY_RETRY_BACKOFF_MAX", 600)
CELERY_DEAD_LETTER_MAX = _resolve_positive_int("celery_dead_letter_max", "AUTOBOT_CELERY_DEAD_LETTER_MAX", 500)


def _claim_task_id(task_id: str) -> bool:
    """Atomically claim *task_id*; False means another delivery already ran it."""
    try:
        client = get_redis_client(database=_REDIS_DATABASE)
        if client is None:
            # Fail open: without Redis there is nothing to dedup against and
            # blocking execution would turn a cache outage into a task outage.
            return True
        return bool(client.set(f"{DEDUP_KEY_PREFIX}{task_id}", "1", nx=True, ex=CELERY_DEDUP_TTL))
    except Exception:
        logger.warning(
            "Idempotency claim failed for task %s — proceeding without dedup",
            task_id,
            exc_info=True,
        )
        return True


def idempotent_task(func: Callable) -> Callable:
    """Skip re-execution when the same task_id was already delivered (#11586).

    Must sit *below* ``@celery_app.task(bind=True)`` so it wraps the task body.
    Retries (``self.request.retries > 0``) bypass the guard: the first attempt
    already holds the claim and a retry is a legitimate re-execution.
    """

    @wraps(func)
    def wrapper(self: Task, *args: Any, **kwargs: Any) -> Any:
        request = getattr(self, "request", None)
        task_id = getattr(request, "id", None)
        retries = getattr(request, "retries", 0) or 0
        if task_id and retries == 0 and not _claim_task_id(task_id):
            logger.warning(
                "Duplicate delivery of task %s (%s) — skipping re-execution",
                self.name,
                task_id,
            )
            return {
                "task_id": task_id,
                "status": TaskStatus.SKIPPED.value,
                "reason": "duplicate_delivery",
            }
        return func(self, *args, **kwargs)

    return wrapper


def _summarize_args(args: Any, kwargs: Any) -> str:
    """Bounded repr of task args/kwargs for the dead-letter record."""
    summary = f"args={args!r} kwargs={kwargs!r}"
    if len(summary) > _ARGS_SUMMARY_MAX_CHARS:
        summary = summary[:_ARGS_SUMMARY_MAX_CHARS] + "…"
    return summary


def park_dead_letter(task_name: str, task_id: str, args_summary: str, error: str) -> None:
    """Record a terminally failed task in the bounded Redis dead-letter list."""
    entry = {
        "task_name": task_name,
        "task_id": task_id,
        "args_summary": args_summary,
        "error": error,
        "status": TaskStatus.PARKED.value,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    logger.error("Celery task parked in dead-letter queue: %s (%s) — %s", task_name, task_id, error)
    try:
        client = get_redis_client(database=_REDIS_DATABASE)
        if client is None:
            return
        pipe = client.pipeline()
        pipe.lpush(DEAD_LETTER_KEY, json.dumps(entry))
        pipe.ltrim(DEAD_LETTER_KEY, 0, CELERY_DEAD_LETTER_MAX - 1)
        pipe.execute()
    except Exception:
        logger.error(
            "Failed to park dead-letter entry for task %s (%s)",
            task_name,
            task_id,
            exc_info=True,
        )


class DeadLetterTask(Task):
    """Celery base task that parks terminal failures for operator review (#11586)."""

    def on_failure(self, exc: BaseException, task_id: str, args: Any, kwargs: Any, einfo: Any) -> None:
        """Celery hook — fires once per task, after retries are exhausted."""
        park_dead_letter(
            task_name=self.name,
            task_id=task_id,
            args_summary=_summarize_args(args, kwargs),
            error=f"{type(exc).__name__}: {exc}",
        )
        super().on_failure(exc, task_id, args, kwargs, einfo)


async def get_dead_letter_status(limit: int = 20) -> Dict[str, Any]:
    """Return the parked-task count plus the *limit* most recent entries."""
    redis = await get_async_redis_client(database=_REDIS_DATABASE)
    if redis is None:
        return {"available": False, "parked": 0, "recent": []}
    count = await redis.llen(DEAD_LETTER_KEY)
    raw_entries = await redis.lrange(DEAD_LETTER_KEY, 0, max(limit, 1) - 1)
    recent = []
    for raw in raw_entries:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        try:
            recent.append(json.loads(text))
        except json.JSONDecodeError:
            recent.append({"raw": text})
    return {"available": True, "parked": count, "recent": recent}


__all__ = [
    "CELERY_DEAD_LETTER_MAX",
    "CELERY_DEDUP_TTL",
    "CELERY_MAX_RETRIES",
    "CELERY_RETRY_BACKOFF_MAX",
    "CELERY_TRANSIENT_ERRORS",
    "DEAD_LETTER_KEY",
    "DEDUP_KEY_PREFIX",
    "DeadLetterTask",
    "get_dead_letter_status",
    "idempotent_task",
    "park_dead_letter",
]
