# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Startup import of the system-knowledge templates into the canonical KB (#19347).

The import (#18577 / #19216) used to run only from the operator CLI: ``get_knowledge_manager``
had no production caller, so a deployed backend never wrote the templates into its KB. This is
the one startup wiring point. Phase 2's ``_init_knowledge_base`` calls
:func:`start_system_knowledge_import` once, right after the knowledge base is published.

* Non-blocking: the import runs as a retained background task (``fire_and_forget``).
* One worker: a :class:`LeaderLease` lets only one uvicorn worker import. The lease is renewed
  while the import runs and is never deleted: it is left to expire, also after a cancelled run,
  so workers that start in the same window skip instead of re-running it. If a renewal fails,
  the import is cancelled: a worker that no longer holds the lease never keeps writing.
* Idempotent: ``SystemKnowledgeManager`` compares the template file-state hash and the per-item
  hashes, so a restart with unchanged templates makes no KB writes.
* A failure is logged and never reaches startup; items that failed to store are counted, logged
  as a warning, and retried on the next start.
"""

from __future__ import annotations

import asyncio
from typing import Any

from autobot_shared.async_compat import fire_and_forget
from autobot_shared.leader_lease import LeaderLease
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

IMPORT_LEASE_KEY = "system_knowledge:import:leader"
IMPORT_TASK_NAME = "system-knowledge-import"


def import_lease() -> LeaderLease:
    """The lease that elects the one worker allowed to run the import."""
    return LeaderLease(key=IMPORT_LEASE_KEY, database="knowledge", label="System knowledge import")


def start_system_knowledge_import(app: Any) -> asyncio.Task | None:
    """Schedule the import once the KB is ready; returns the retained task, or None.

    Never raises: a scheduling failure is logged, so the KB wiring around the call still runs.
    """
    knowledge_base = getattr(app.state, "knowledge_base", None)
    if knowledge_base is None:
        logger.warning("System knowledge import skipped: knowledge base not ready")
        return None
    coro = run_system_knowledge_import(knowledge_base)
    try:
        return fire_and_forget(coro, name=IMPORT_TASK_NAME)
    except Exception as exc:
        coro.close()
        logger.error("System knowledge import not scheduled; startup continues: %s", exc, exc_info=True)
        return None


async def run_system_knowledge_import(knowledge_base: Any, lease: LeaderLease | None = None) -> bool:
    """Import the templates if this worker wins the lease, and only while it keeps it.

    True only when the import ran with no failed item. False when another worker holds the lease,
    the lease was lost mid-run (the import is cancelled), the import raised, or some items failed
    to store (those are retried on the next start).
    """
    lease = lease or import_lease()
    try:
        if not await lease.update_leadership():
            logger.info("System knowledge import: lease not acquired (another worker or no Redis), skipping")
            return False
        completed, failures = await _import_while_leading(knowledge_base, lease)
    except Exception as exc:
        logger.error("System knowledge import failed; startup continues: %s", exc, exc_info=True)
        return False
    return completed and _report(failures)


async def _import_while_leading(knowledge_base: Any, lease: LeaderLease) -> tuple[bool, list[str]]:
    """Race the import against the lease keeper: (completed, failed items).

    ``completed`` is False when the lease was lost first; the import is then cancelled.
    """
    import_task = asyncio.create_task(_import(knowledge_base), name=f"{IMPORT_TASK_NAME}-run")
    keeper = asyncio.create_task(_keep_lease(lease), name=f"{IMPORT_TASK_NAME}-lease")
    try:
        await asyncio.wait({import_task, keeper}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        keeper.cancel()
        if not import_task.done():
            import_task.cancel()
    if not import_task.cancelled() and import_task.done():
        return True, import_task.result()
    await asyncio.gather(import_task, return_exceptions=True)
    renewal_error = None if keeper.cancelled() else keeper.exception()
    logger.error(
        "System knowledge import cancelled: this worker lost the import lease mid-run (renewal error: %r)",
        renewal_error,
    )
    return False, []


def _report(failures: list[str]) -> bool:
    """Log the outcome truthfully; a failed item makes the run unsuccessful."""
    if failures:
        logger.warning(
            "System knowledge import incomplete: %d item(s) failed and will retry on the next start: %s",
            len(failures),
            ", ".join(failures),
        )
        return False
    logger.info("System knowledge import finished with no failed item")
    return True


async def _import(knowledge_base: Any) -> list[str]:
    """Run the import through the one entry point, the ``KnowledgeManager`` facade; return failed items."""
    from agents.knowledge_manager import get_knowledge_manager

    # Machine-aware mode adapts per-host copies and never imports the base templates; temporal
    # tracking is not part of the import. Both stay off here.
    manager = await asyncio.to_thread(
        get_knowledge_manager, knowledge_base, enable_temporal=False, enable_machine_aware=False
    )
    await manager.initialize()
    return manager.import_failures


async def _keep_lease(lease: LeaderLease) -> None:
    """Renew the lease while the import runs; return as soon as a renewal fails, which ends the import."""
    while True:
        await asyncio.sleep(lease.refresh_s)
        if not await lease.update_leadership():
            logger.warning("System knowledge import lost its lease mid-run; cancelling the import")
            return
