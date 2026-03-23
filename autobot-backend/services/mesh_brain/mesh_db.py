# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Async PostgreSQL client for Neural Mesh RAG graph operations (#2055)."""
import logging
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


class MeshDB:
    """Async PostgreSQL client for mesh_nodes, mesh_edges, and mesh_evolution_log."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    async def create_node(
        self,
        chunk_id: str,
        source_file: Optional[str],
        node_type: str,
        raptor_level: int = 0,
    ) -> str:
        """Insert a mesh node and return its UUID string (#2055)."""
        sql = text(
            """
            INSERT INTO mesh_nodes (chunk_id, source_file, node_type, raptor_level)
            VALUES (:chunk_id, :source_file, :node_type, :raptor_level)
            RETURNING id::text
            """
        )
        async with self.engine.begin() as conn:
            row = await conn.execute(
                sql,
                {
                    "chunk_id": chunk_id,
                    "source_file": source_file,
                    "node_type": node_type,
                    "raptor_level": raptor_level,
                },
            )
            node_id = row.scalar_one()
        logger.info("Created mesh node %s chunk_id=%s", node_id, chunk_id)
        return node_id

    async def update_access_count(self, node_ids: list[str]) -> None:
        """Increment access_count and set last_accessed for the given node UUIDs (#2055)."""
        if not node_ids:
            return
        sql = text(
            """
            UPDATE mesh_nodes
            SET access_count = access_count + 1,
                last_accessed = NOW()
            WHERE id = ANY(:node_ids::uuid[])
            """
        )
        async with self.engine.begin() as conn:
            await conn.execute(sql, {"node_ids": node_ids})
        logger.debug("Updated access_count for %d nodes", len(node_ids))

    # ------------------------------------------------------------------
    # Edges
    # ------------------------------------------------------------------

    async def create_edge(
        self,
        from_node: str,
        to_node: str,
        edge_type: str,
        weight: float,
        origin: str,
    ) -> str:
        """Insert a mesh edge and return its UUID string (#2055)."""
        sql = text(
            """
            INSERT INTO mesh_edges (from_node, to_node, edge_type, weight, origin)
            VALUES (:from_node::uuid, :to_node::uuid, :edge_type, :weight, :origin)
            RETURNING id::text
            """
        )
        async with self.engine.begin() as conn:
            row = await conn.execute(
                sql,
                {
                    "from_node": from_node,
                    "to_node": to_node,
                    "edge_type": edge_type,
                    "weight": weight,
                    "origin": origin,
                },
            )
            edge_id = row.scalar_one()
        logger.info(
            "Created mesh edge %s %s->%s type=%s",
            edge_id,
            from_node,
            to_node,
            edge_type,
        )
        return edge_id

    async def get_edge(
        self,
        from_node: str,
        to_node: str,
        edge_type: Optional[str] = None,
    ) -> Optional[dict]:
        """Return the first matching edge as a dict, or None if absent (#2055)."""
        if edge_type is not None:
            sql = text(
                """
                SELECT id::text, from_node::text, to_node::text,
                       edge_type, weight, origin, co_access_count, last_reinforced
                FROM mesh_edges
                WHERE from_node = :from_node::uuid
                  AND to_node   = :to_node::uuid
                  AND edge_type = :edge_type
                LIMIT 1
                """
            )
            params: dict[str, Any] = {
                "from_node": from_node,
                "to_node": to_node,
                "edge_type": edge_type,
            }
        else:
            sql = text(
                """
                SELECT id::text, from_node::text, to_node::text,
                       edge_type, weight, origin, co_access_count, last_reinforced
                FROM mesh_edges
                WHERE from_node = :from_node::uuid
                  AND to_node   = :to_node::uuid
                LIMIT 1
                """
            )
            params = {"from_node": from_node, "to_node": to_node}

        async with self.engine.connect() as conn:
            row = await conn.execute(sql, params)
            result = row.mappings().fetchone()
        return dict(result) if result else None

    async def update_edge(
        self,
        edge_id: str,
        weight: Optional[float] = None,
        co_access_count: Optional[int] = None,
    ) -> None:
        """Partially update an edge's weight and/or co_access_count (#2055)."""
        updates: list[str] = ["last_reinforced = NOW()"]
        params: dict[str, Any] = {"edge_id": edge_id}
        if weight is not None:
            updates.append("weight = :weight")
            params["weight"] = weight
        if co_access_count is not None:
            updates.append("co_access_count = :co_access_count")
            params["co_access_count"] = co_access_count
        sql = text(
            f"UPDATE mesh_edges SET {', '.join(updates)} WHERE id = :edge_id::uuid"
        )
        async with self.engine.begin() as conn:
            await conn.execute(sql, params)
        logger.debug("Updated edge %s", edge_id)

    async def get_neighbors(
        self,
        node_id: str,
        min_weight: float = 0.0,
        max_hops: int = 1,
    ) -> list[dict]:
        """Return direct neighbors of node_id above min_weight (max_hops=1 only) (#2055)."""
        sql = text(
            """
            SELECT e.id::text        AS edge_id,
                   e.to_node::text   AS neighbor_id,
                   e.edge_type,
                   e.weight,
                   e.origin
            FROM mesh_edges e
            WHERE e.from_node = :node_id::uuid
              AND e.weight    >= :min_weight
            ORDER BY e.weight DESC
            """
        )
        async with self.engine.connect() as conn:
            rows = await conn.execute(
                sql, {"node_id": node_id, "min_weight": min_weight}
            )
            return [dict(r) for r in rows.mappings()]

    async def fetch_edges(self, min_weight: float = 0.5) -> list[dict]:
        """Return all edges above min_weight. Satisfies MeshEdgeSync Protocol (#2029, #2055)."""
        sql = text(
            """
            SELECT id::text, from_node::text, to_node::text,
                   edge_type, weight, origin
            FROM mesh_edges
            WHERE weight >= :min_weight
            ORDER BY weight DESC
            """
        )
        async with self.engine.connect() as conn:
            rows = await conn.execute(sql, {"min_weight": min_weight})
            return [dict(r) for r in rows.mappings()]

    async def get_co_access_count(self, node_a: str, node_b: str) -> int:
        """Return the co_access_count for the edge between node_a and node_b (#2055)."""
        sql = text(
            """
            SELECT COALESCE(co_access_count, 0)
            FROM mesh_edges
            WHERE from_node = :node_a::uuid
              AND to_node   = :node_b::uuid
            LIMIT 1
            """
        )
        async with self.engine.connect() as conn:
            row = await conn.execute(sql, {"node_a": node_a, "node_b": node_b})
            return row.scalar() or 0

    # ------------------------------------------------------------------
    # Evolution log
    # ------------------------------------------------------------------

    async def log_evolution(
        self,
        event_type: str,
        entity_id: Optional[str],
        old_value: Optional[dict],
        new_value: Optional[dict],
        actor: str,
    ) -> None:
        """Append an audit entry to mesh_evolution_log (#2055)."""
        sql = text(
            """
            INSERT INTO mesh_evolution_log
                (event_type, entity_id, old_value, new_value, actor)
            VALUES
                (:event_type,
                 :entity_id::uuid,
                 :old_value::jsonb,
                 :new_value::jsonb,
                 :actor)
            """
        )
        import json

        async with self.engine.begin() as conn:
            await conn.execute(
                sql,
                {
                    "event_type": event_type,
                    "entity_id": entity_id,
                    "old_value": json.dumps(old_value)
                    if old_value is not None
                    else None,
                    "new_value": json.dumps(new_value)
                    if new_value is not None
                    else None,
                    "actor": actor,
                },
            )
        logger.debug("Logged evolution event %s entity=%s", event_type, entity_id)
