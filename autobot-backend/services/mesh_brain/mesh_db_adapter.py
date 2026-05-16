# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Concrete MeshGraph/MeshDB adapter bridging PostgreSQL mesh schema to protocol interfaces (#2548).

The ``mesh_db.py`` module defines ``MeshDB`` — a full-featured async PostgreSQL client
for the mesh tables introduced in #2055.  That class already satisfies every method
required by the ``MeshDB`` Protocol in ``edge_learner.py``.

The only gap is the ``MeshGraph`` Protocol defined in ``staleness_propagator.py``:

    async def get_neighbors(self, node_id: str) -> list[tuple[str, float]]: ...

``MeshDB.get_neighbors()`` returns ``list[dict]`` (with ``neighbor_id``, ``weight``, …)
whereas ``MeshGraph.get_neighbors()`` expects ``list[tuple[str, float]]``.

``MeshDBAdapter`` wraps the concrete ``MeshDB`` instance and:

- Forwards all ``MeshDB`` Protocol calls (``get_edge``, ``update_edge``, ``create_edge``,
  ``get_co_access_count``, ``update_access_count``) unchanged to the underlying client.
- Implements ``MeshGraph.get_neighbors()`` by delegating to ``MeshDB.get_neighbors()``
  and reshaping the result into the ``[(neighbor_id, weight)]`` tuples the BFS
  propagator expects.

Use ``create_mesh_db_adapter()`` at application startup to get an engine-wired instance.
"""

from sqlalchemy.ext.asyncio import AsyncEngine

from autobot_shared.logging_manager import get_logger
from services.mesh_brain.mesh_db import MeshDB

logger = get_logger(__name__)


class MeshDBAdapter:
    """Adapter that satisfies both the ``MeshDB`` and ``MeshGraph`` protocols (#2548).

    Delegates all ``MeshDB`` operations to the wrapped ``MeshDB`` instance.
    The only transformation applied is in ``get_neighbors()``: the dict rows
    returned by ``MeshDB.get_neighbors()`` are projected to ``(neighbor_id, weight)``
    tuples so the result matches the ``MeshGraph`` Protocol signature consumed by
    ``propagate_staleness()``.
    """

    def __init__(self, db: MeshDB) -> None:
        self._db = db
        logger.debug("MeshDBAdapter initialised wrapping %r", db)

    # ------------------------------------------------------------------
    # MeshDB protocol — EdgeLearner surface
    # ------------------------------------------------------------------

    async def get_edge(self, node_a: str, node_b: str) -> dict | None:
        """Return the first edge between ``node_a`` and ``node_b``, or ``None``."""
        return await self._db.get_edge(node_a, node_b)

    async def update_edge(self, edge_id: str, **kwargs) -> None:
        """Partially update an edge's mutable fields."""
        await self._db.update_edge(edge_id, **kwargs)

    async def create_edge(self, from_node: str, to_node: str, **kwargs) -> None:
        """Insert a new mesh edge; keyword arguments are forwarded to ``MeshDB.create_edge``."""
        await self._db.create_edge(from_node, to_node, **kwargs)

    async def get_co_access_count(self, node_a: str, node_b: str) -> int:
        """Return the co_access_count for the edge between ``node_a`` and ``node_b``."""
        return await self._db.get_co_access_count(node_a, node_b)

    async def update_access_count(self, node_ids: list[str]) -> None:
        """Increment access_count and set last_accessed for the given node UUIDs."""
        await self._db.update_access_count(node_ids)

    async def get_anchor_neighbors(self, seed_ids: list[str]) -> list[str]:
        """Return IDs of anchor nodes adjacent to any seed_id (#4819)."""
        return await self._db.get_anchor_neighbors(seed_ids)

    async def fetch_edges(self, min_weight: float = 0.5) -> list[dict]:
        """Return all edges above min_weight. Satisfies MeshEdgeSync Protocol (#4837)."""
        return await self._db.fetch_edges(min_weight=min_weight)

    async def promote_to_anchor(self, node_id: str) -> None:
        """Set is_anchor=True for node_id. Forwards to MeshDB (#4837)."""
        await self._db.promote_to_anchor(node_id)

    # ------------------------------------------------------------------
    # MeshGraph protocol — StalenessPropagor surface
    # ------------------------------------------------------------------

    async def get_neighbors(self, node_id: str) -> list[tuple[str, float]]:
        """Return ``[(neighbor_id, weight)]`` tuples for ``node_id``.

        Delegates to ``MeshDB.get_neighbors()`` (returns ``list[dict]``) and
        projects each row to the ``(neighbor_id, weight)`` tuple shape required
        by the ``MeshGraph`` Protocol in ``staleness_propagator.py``.
        """
        rows = await self._db.get_neighbors(node_id, min_weight=0.0)
        result: list[tuple[str, float]] = [(row["neighbor_id"], float(row["weight"])) for row in rows]
        logger.debug(
            "MeshDBAdapter.get_neighbors node=%s found=%d neighbors",
            node_id,
            len(result),
        )
        return result


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_mesh_db_adapter(engine: AsyncEngine) -> MeshDBAdapter:
    """Construct a ``MeshDBAdapter`` wired to ``engine`` (#2548).

    Intended to be called once at application startup, for example::

        from user_management.database import get_async_engine
        from services.mesh_brain.mesh_db_adapter import create_mesh_db_adapter

        adapter = create_mesh_db_adapter(get_async_engine())
        edge_learner = EdgeLearner(db=adapter, redis=redis_client)

    Args:
        engine: An initialised ``AsyncEngine`` for the PostgreSQL mesh database.

    Returns:
        A ``MeshDBAdapter`` instance that satisfies both ``MeshDB`` and ``MeshGraph``
        protocols.
    """
    db = MeshDB(engine)
    adapter = MeshDBAdapter(db)
    logger.info("MeshDBAdapter created with engine %r", engine)
    return adapter
