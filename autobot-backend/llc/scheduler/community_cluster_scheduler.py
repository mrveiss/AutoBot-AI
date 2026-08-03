# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC community-clustering scheduler (#4834, #13210).

Runs every 6 hours. Builds a NetworkX graph from MeshDB edges, runs community
detection, and promotes the highest-degree node in each community to an
anchor node so NeuralMeshRetriever's anchor seeding stays fresh.

Previously hand-rolled as a bare ``while True`` loop inside
``initialization/lifespan.py`` (GH#4834). That copy diverged from the
cancellation-safety contract ``PollLoopScheduler`` already provides to every
other LLC scheduler (LivenessMonitor, BudgetWatchdog, SessionCheckpointer):
its ``honour_pending_cancellation()`` call lived only in the ``except`` arm
(the exact defect #13203 fixed for the other three) and its shutdown drain
was an unbounded, unshielded ``asyncio.gather(task)`` (the exact defect
#13203's ``aclose()`` bound). Subclassing ``PollLoopScheduler`` instead of
copy-pasting a second implementation of both fixes is deliberate — one
correct, tested implementation of the pattern.
"""

import asyncio
import logging
from typing import Any

from .base import PollLoopScheduler

logger = logging.getLogger(__name__)

_CLUSTER_INTERVAL_SECONDS = 6 * 3600  # 6 hours
_INITIAL_DELAY_SECONDS = 300  # let startup finish before the first expensive pass

# Indirection so a test can patch just this module's initial-delay sleep
# (``patch("llc.scheduler.community_cluster_scheduler._sleep", ...)``)
# without reaching through to ``asyncio.sleep`` on the shared ``asyncio``
# module object, which would affect every other coroutine in the process for
# the duration of the patch.
_sleep = asyncio.sleep


class CommunityClusteringScheduler(PollLoopScheduler):
    """Periodic community-clustering pass over the mesh graph."""

    _task_name = "llc-community-clusterer"

    def __init__(self, mesh_db: Any, poll_interval: float = _CLUSTER_INTERVAL_SECONDS) -> None:
        super().__init__(poll_interval)
        self._mesh_db = mesh_db
        self._first_tick = True

    def start(self) -> None:
        """Start the background polling loop."""
        if super().start():
            logger.info(
                "CommunityClusterer: periodic loop started (interval=%dh)",
                int(self._poll_interval // 3600),
            )

    async def _tick(self) -> None:
        if self._first_tick:
            self._first_tick = False
            # A bare sleep, not driver code — a cancellation delivered here
            # propagates as a real CancelledError, no masking possible.
            await _sleep(_INITIAL_DELAY_SECONDS)

        from services.mesh_brain.community_clusterer import CommunityClusterer

        promoted = await CommunityClusterer(self._mesh_db).run()
        logger.info("CommunityClusterer periodic run: %d anchors promoted", len(promoted))
