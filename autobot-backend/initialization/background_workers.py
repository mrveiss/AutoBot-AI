# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Long-lived background workers started with the app (#4453, #17548).

Extracted from ``lifespan.py`` in #17548, which needed to add a worker to a file already
far past its recorded ceiling and had to find the room by splitting rather than raising.

What belongs here: a task that runs for the process's lifetime and is *started*, not
awaited. Each starter keeps its task on ``app.state`` — a task nobody holds a reference
to can be garbage-collected mid-flight, and the symptom of that is a worker that silently
stops rather than one that errors.

Each starter is also non-fatal: a background reconciler failing to start must not take the
backend down with it. It must, however, say so loudly, because the alternative is exactly
the #17548 defect — a worker that is not running and looks like one that is.
"""

import asyncio

from fastapi import FastAPI

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


async def start_doc_sync_queue_worker(app: FastAPI) -> None:
    """Start the persistent document sync queue worker (#4453).

    The worker drains :class:`DocumentSyncQueue` so re-indexing survives crashes, retries
    up to MAX_ATTEMPTS, and respects priority ordering.
    """
    try:
        from services.knowledge.sync_queue import SyncQueueWorker

        worker = SyncQueueWorker()
        task = asyncio.create_task(worker.run())
        app.state.doc_sync_queue_worker = worker
        app.state.doc_sync_queue_worker_task = task
        logger.info("✅ Doc Sync Queue: worker started")
    except Exception as e:  # noqa: BLE001
        logger.warning("Doc sync queue worker failed to start: %s", e)


async def start_vector_reconciler(app: FastAPI) -> None:
    """Start the KB vector reconciler (#17548).

    ``store_authority`` names ``background_vectorization`` as what rebuilds the ChromaDB
    projection of ``knowledge_facts``. The loop was complete and had no caller, so that
    half of the contract ran only when someone hit an endpoint — a vector lost between
    requests stayed lost, which is the drift #12733 recorded and ``vector_seen_at`` exists
    to measure.

    The knowledge base must already be on ``app.state``; this is ordered after
    ``_init_knowledge_base`` for that reason. Without it there is nothing to reconcile
    against, and starting anyway would produce a task that logs failures for ever.
    """
    kb = getattr(app.state, "knowledge_base", None)
    if kb is None:
        logger.warning("KB vector reconciler NOT started: no knowledge base on app.state (#17548)")
        return
    try:
        from background_vectorization import CHECK_INTERVAL_SECONDS, get_background_vectorizer

        vectorizer = get_background_vectorizer()
        task = asyncio.create_task(vectorizer.periodic_check(kb), name="kb-vector-reconciler")
        app.state.vector_reconciler_task = task
        logger.info("✅ KB Vector Reconciler: started, every %ds", CHECK_INTERVAL_SECONDS)
    except Exception as e:  # noqa: BLE001
        logger.warning("KB vector reconciler failed to start: %s", e)


async def start_background_workers(app: FastAPI) -> None:
    """Start every lifetime worker, in one call from the lifespan.

    One entry point rather than one line per worker: ``initialize_background_services``
    is at its length limit, so each new worker would otherwise have to buy its line by
    shortening something else — a pressure that eventually gets paid by not adding the
    worker at all, which is how #17548 happened.
    """
    await start_doc_sync_queue_worker(app)
    await start_vector_reconciler(app)


__all__ = ["start_background_workers", "start_doc_sync_queue_worker", "start_vector_reconciler"]
