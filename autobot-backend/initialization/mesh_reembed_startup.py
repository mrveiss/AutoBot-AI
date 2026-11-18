# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Startup and shutdown of the ``mesh:reembed_queue`` consumer (#20535).

Lives beside ``lifespan.py`` because that file is at its size ceiling.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


async def start_mesh_reembed_consumer(app: Any) -> None:
    """Start the consumer of mesh:reembed_queue; on by default.

    Unlike MeshBrainScheduler it deletes nothing: it only hands flagged doc ids to
    the document re-index queue, so it is not tied to that scheduler's flag. A
    LeaderLease keeps it to one worker.
    """
    app.state.mesh_reembed_consumer = None
    try:
        from services.mesh_brain import reembed_consumer

        if not reembed_consumer.ENABLED:
            logger.info("Mesh re-embed consumer: disabled (AUTOBOT_MESH_REEMBED_ENABLED=false)")
            return
        consumer, task = await reembed_consumer.start_reembed_consumer()
        app.state.mesh_reembed_consumer = consumer
        app.state.mesh_reembed_task = task
        logger.info("Mesh re-embed consumer: started")
    except Exception as exc:
        logger.warning("Mesh re-embed consumer startup failed (non-fatal): %s", exc)


async def stop_mesh_reembed_consumer(app: Any) -> None:
    """Cancel the consumer task and free its lease so another worker can take over."""
    consumer = getattr(app.state, "mesh_reembed_consumer", None)
    if consumer:
        task = app.state.mesh_reembed_task
        task.cancel()
        # Wait for the loop to stop (it may be mid-drain) before freeing the lease, so a successor
        # never starts while this worker still touches the queue.
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await consumer.lease.release()
