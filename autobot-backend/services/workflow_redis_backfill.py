# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Copy Redis-persisted workflows into the durable ``workflows`` table (#14210).

``api/workflow_state.py``'s ``WorkflowStateMachine`` is the crash-recoverable
store for workflows created through the orchestration path — real user data,
unlike the plain in-memory ``active_workflows`` dict in ``api/workflow.py``
(process-local, already erased on every restart; nothing here or elsewhere
can recover that half after the fact, since a script cannot reach another
process's memory).

Neither ``WorkflowState`` (the Pydantic model persisted to Redis) nor the
in-memory dict carries a ``company_id`` field — #14210's audit confirmed no
producer of a workflow has ever recorded which company it belongs to. That
means a Redis-persisted workflow genuinely CANNOT be attributed to a company;
guessing one would be worse than leaving it unattributed (a silently wrong
company scope is exactly the class of defect #13936/#13969/#13942/#14222
exist to prevent).

Per the no-data-loss rule, this is additive-only and REPAIR-PATH shaped
(mirrors ``chat_history/session_reply_backfill.py``): it copies each
Redis-persisted workflow into ``workflows`` with ``company_id=NULL`` and
``source=SOURCE_LEGACY_REDIS`` (models/workflow.py), and NEVER deletes or
mutates the Redis key — Redis stays the authoritative store for these rows
until a future reconciliation pass (#14210's explicitly deferred "step 2")
retires it. Already-migrated workflow_ids are skipped (idempotent re-run).

Not auto-run: no scheduled/Celery hook, no import-time side effect. Requires
an explicit CLI invocation naming ``--dry-run`` or not — an operator decides
when to run this, the same way ``session_reply_backfill.py`` requires
explicit ``--session-id`` arguments.

Usage::

    python -m services.workflow_redis_backfill [--dry-run]

Exit code is always 0 on a successful scan (even with zero migratable rows);
scan/connection failures propagate as an unhandled exception.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass, field
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.workflow_state import ACTIVE_SET, KEY_PREFIX
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from llc.models.enums import WorkflowStatus
from models.workflow import SOURCE_LEGACY_REDIS, Workflow
from user_management.database import get_async_session_factory

logger = get_logger(__name__)

REDIS_DATABASE = "workflows"


@dataclass
class BackfillReport:
    """Outcome of one backfill run, for the CLI summary and tests."""

    scanned: int = 0
    migrated: List[str] = field(default_factory=list)
    already_present: List[str] = field(default_factory=list)
    unparseable: List[str] = field(default_factory=list)


async def _scan_redis_workflow_keys() -> List[str]:
    """Every persisted workflow key, active or completed-with-TTL.

    ``WorkflowStateMachine.list_active`` only returns the active set — a
    completed workflow is removed from that set (though its key survives
    under its 7-day TTL, see ``COMPLETED_TTL``). SCAN over the key prefix
    reaches both.
    """
    redis = await get_async_redis_client(database=REDIS_DATABASE)
    if redis is None:
        return []
    keys: List[str] = []
    async for raw_key in redis.scan_iter(match=f"{KEY_PREFIX}*"):
        key = raw_key.decode("utf-8") if isinstance(raw_key, bytes) else raw_key
        if key == ACTIVE_SET:
            continue
        keys.append(key)
    return keys


def _legacy_status(blob: dict) -> str:
    """Map a legacy Redis blob onto ``WorkflowStatus`` (#14210).

    The previous form wrote ``blob["current_step"]`` straight into ``status`` —
    a *step name* in a *status* column, so the field held a mix of lifecycle
    states and arbitrary step identifiers from the first row. Nothing is lost by
    normalising: the entire blob is preserved verbatim in ``definition``, so the
    original ``current_step`` survives and can be re-read at any time.

    A blob carrying a ``current_step`` had begun executing, so ``RUNNING`` is the
    honest reading — not ``PLANNED``, which would claim it never started.
    """
    if blob.get("errors"):
        return WorkflowStatus.FAILED.value
    if blob.get("current_step"):
        return WorkflowStatus.RUNNING.value
    return WorkflowStatus.PLANNED.value


async def backfill(*, dry_run: bool = False, session: AsyncSession | None = None) -> BackfillReport:
    """Copy every Redis-persisted workflow into the ``workflows`` table.

    Args:
        dry_run: When True, scans and reports but writes nothing.
        session: Injected session for tests; a fresh one is opened when
            omitted.
    """
    report = BackfillReport()
    redis = await get_async_redis_client(database=REDIS_DATABASE)
    if redis is None:
        logger.warning("Redis unavailable for database=%s — nothing to backfill", REDIS_DATABASE)
        return report

    keys = await _scan_redis_workflow_keys()
    report.scanned = len(keys)

    owns_session = session is None
    if owns_session:
        factory = get_async_session_factory()
        session = factory()

    try:
        for key in keys:
            workflow_id = key[len(KEY_PREFIX) :]
            raw = await redis.get(key)
            if raw is None:
                continue
            try:
                blob = json.loads(raw)
            except (TypeError, ValueError):
                logger.warning("Unparseable workflow JSON at %s — leaving Redis untouched", key)
                report.unparseable.append(workflow_id)
                continue

            # #14271: workflow_id is no longer a global primary key, so a bare
            # `WHERE workflow_id = :id` can now match more than one row (one
            # per company that happens to share the string) and
            # scalar_one_or_none() would raise MultipleResultsFound. Scope to
            # company_id IS NULL — every row this script itself writes — so
            # this asks the only question that matters here: "has this exact
            # Redis-origin key already been imported", not "does any company
            # happen to use this string".
            existing = await session.execute(
                select(Workflow.workflow_id).where(
                    Workflow.workflow_id == workflow_id,
                    Workflow.company_id.is_(None),
                )
            )
            if existing.scalar_one_or_none() is not None:
                report.already_present.append(workflow_id)
                continue

            if not dry_run:
                session.add(
                    Workflow(
                        workflow_id=workflow_id,
                        company_id=None,  # unattributable — see module docstring
                        name=blob.get("goal"),
                        status=_legacy_status(blob),
                        source=SOURCE_LEGACY_REDIS,
                        definition=blob,
                    )
                )
            report.migrated.append(workflow_id)

        if not dry_run:
            await session.commit()
    finally:
        if owns_session:
            await session.close()

    return report


async def _main(dry_run: bool) -> None:
    report = await backfill(dry_run=dry_run)
    logger.info(
        "Redis workflow backfill %s: scanned=%d migrated=%d already_present=%d unparseable=%d",
        "(dry-run)" if dry_run else "complete",
        report.scanned,
        len(report.migrated),
        len(report.already_present),
        len(report.unparseable),
    )
    if report.migrated:
        logger.info(
            "Migrated workflow_ids (company_id=NULL — unattributed, needs reconciliation): %s",
            report.migrated,
        )
    if report.unparseable:
        logger.warning("Unparseable workflow_ids (left untouched in Redis): %s", report.unparseable)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill Redis-persisted workflows into the workflows table (#14210)."
    )
    parser.add_argument("--dry-run", action="store_true", help="Scan and report without writing.")
    args = parser.parse_args()
    asyncio.run(_main(args.dry_run))
