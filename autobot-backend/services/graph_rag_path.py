# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Graph-RAG shortest-path query (split out of ``graph_rag_service`` in #18825)."""

import asyncio
import time
from typing import Any, Dict

from autobot_shared.logging_manager import get_llm_logger
from constants.rag_graph_constants import RAG_GRAPH_PATH_DEPTH

logger = get_llm_logger("graph_rag_service")


def _log_connection_path(from_entity: str, to_entity: str, result: Dict[str, Any]) -> None:
    """One line per traversal: the endpoints, the verdict and the cost."""
    logger.info(
        "Connection path '%s' -> '%s': found=%s reason=%s hops=%s in %.3fs",
        from_entity,
        to_entity,
        result.get("found"),
        result.get("reason"),
        result.get("hops"),
        result["traversal_time"],
    )


class GraphPathMixin:
    """Mixin providing ``find_connection_path``; relies on ``self.graph``."""

    async def find_connection_path(
        self,
        from_entity: str,
        to_entity: str,
        relation: str | None = None,
        max_depth: int = RAG_GRAPH_PATH_DEPTH,
        direction: str = "both",
        timeout: float | None = None,
        *,
        owner: Any,
    ) -> Dict[str, Any]:
        """
        Answer "how are these two things connected" with a shortest graph path.

        Issue #13474: ``graph_aware_search`` only expands a *neighbourhood* — it
        can say what relates to X, never how X reaches Y. This exposes the memory
        graph's shortest-path traversal, which #8198 implemented and left without
        a production caller.

        Args:
            from_entity: Source entity name.
            to_entity: Target entity name.
            relation: Restrict traversal to this relation type; None = all.
            max_depth: Maximum path length to search.
            direction: ``"outgoing"``, ``"incoming"``, or ``"both"``.
            timeout: Traversal deadline in seconds; None leaves it unbounded.
            owner: REQUIRED OwnerScope / UNSCOPED_ALL_USERS (#18825).

        Returns:
            The ``AutoBotMemoryGraph.find_path`` result dict plus
            ``traversal_time``. Failures are not swallowed into "no path" — a
            broken traversal raises so the caller reports an error, not an answer.
            A timeout raises ``asyncio.TimeoutError`` for the same reason: an
            abandoned walk is not evidence that two entities are unconnected.
        """
        start_time = time.perf_counter()
        traversal = self.graph.find_path(
            from_entity=from_entity,
            to_entity=to_entity,
            relation=relation,
            max_depth=max_depth,
            direction=direction,
            owner=owner,
        )
        result = await (asyncio.wait_for(traversal, timeout) if timeout else traversal)
        result["traversal_time"] = time.perf_counter() - start_time
        _log_connection_path(from_entity, to_entity, result)
        return result
