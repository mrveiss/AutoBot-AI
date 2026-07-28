# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Memory consolidation Celery task (GH#11263).

Periodically compacts the ``trajectories`` ChromaDB collection so retrieval
precision does not degrade as the store grows: duplicate near-identical turns are
collapsed to their best-reward survivor and stale low-reward failures are pruned.

Registered in ``celery_app.py`` beat schedule under ``memory.consolidate_trajectories``
(priority tier NORMAL, GH#11262). Runs as a normal Beat task; the heavy lifting
lives in ``TrajectoryStore.consolidate`` which is fully delete-only.
"""

import os

from autobot_shared.async_compat import run_or_schedule
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import utc_timestamp
from celery_app import celery_app

logger = get_logger(__name__)

_LAST_RUN_KEY = "memory:consolidate_trajectories:last_run"
_FACTS_LAST_RUN_KEY = "memory:consolidate_facts:last_run"

# A3 (#12554): first ship enforces nothing — the task logs prune candidates until
# the counts are reviewed, then this flips to False (or is overridden per run).
_FACTS_CONSOLIDATE_DRY_RUN = os.environ.get("AUTOBOT_FACTS_CONSOLIDATE_DRY_RUN", "1").lower() not in (
    "0",
    "false",
    "no",
)


def _get_redis():
    """Sync Redis client (analytics DB) for last-run bookkeeping."""
    from autobot_shared.redis_client import get_redis_client

    return get_redis_client(async_client=False, database="analytics")


async def _run_consolidation() -> dict:
    """Open the store and run one consolidation pass, returning its summary."""
    from memory.trajectory_store import get_trajectory_store

    store = await get_trajectory_store()
    return await store.consolidate()


@celery_app.task(bind=True, name="memory.consolidate_trajectories")
def consolidate_trajectories(self) -> dict:
    """Daily task: dedupe + prune the trajectory store, then record the run time."""
    run_at = utc_timestamp()
    summary = run_or_schedule(_run_consolidation())
    try:
        _get_redis().set(_LAST_RUN_KEY, run_at)
    except Exception as exc:  # noqa: BLE001 — bookkeeping only, never fail the task
        logger.debug("consolidate_trajectories: last-run write skipped: %s", exc)
    logger.info("consolidate_trajectories complete at %s: %s", run_at, summary)
    return {"status": "success", "run_at": run_at, **(summary or {})}


async def _run_facts_consolidation() -> dict:
    """Open the knowledge base and run one fact-lane consolidation pass."""
    from knowledge._composed import get_knowledge_base

    kb = await get_knowledge_base()
    return await kb.consolidate_facts(dry_run=_FACTS_CONSOLIDATE_DRY_RUN)


@celery_app.task(bind=True, name="memory.consolidate_facts")
def consolidate_facts(self) -> dict:
    """Nightly task: decay/prune genuinely-dead essential-story facts (A3 #12554).

    Delete-only and guarded (owned/verified/pinned never eligible); ships in
    dry-run by default so candidates are logged before any deletion is enforced.
    """
    run_at = utc_timestamp()
    summary = run_or_schedule(_run_facts_consolidation())
    try:
        _get_redis().set(_FACTS_LAST_RUN_KEY, run_at)
    except Exception as exc:  # noqa: BLE001 — bookkeeping only, never fail the task
        logger.debug("consolidate_facts: last-run write skipped: %s", exc)
    logger.info("consolidate_facts complete at %s: %s", run_at, summary)
    return {"status": "success", "run_at": run_at, **(summary or {})}
