# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Async PostgreSQL client for Neural Mesh RAG graph operations (#2055)."""

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


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
        source_file: str | None,
        node_type: str,
        raptor_level: int = 0,
    ) -> str:
        """Insert a mesh node and return its UUID string (#2055)."""
        sql = text("""
            INSERT INTO mesh_nodes (chunk_id, source_file, node_type, raptor_level)
            VALUES (:chunk_id, :source_file, :node_type, :raptor_level)
            RETURNING id::text
            """)
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
        sql = text("""
            UPDATE mesh_nodes
            SET access_count = access_count + 1,
                last_accessed = NOW()
            WHERE id = ANY(:node_ids::uuid[])
            """)
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
        sql = text("""
            INSERT INTO mesh_edges (from_node, to_node, edge_type, weight, origin)
            VALUES (:from_node::uuid, :to_node::uuid, :edge_type, :weight, :origin)
            RETURNING id::text
            """)
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
        edge_type: str | None = None,
    ) -> dict | None:
        """Return the first matching edge as a dict, or None if absent (#2055)."""
        if edge_type is not None:
            sql = text("""
                SELECT id::text, from_node::text, to_node::text,
                       edge_type, weight, origin, co_access_count, last_reinforced
                FROM mesh_edges
                WHERE from_node = :from_node::uuid
                  AND to_node   = :to_node::uuid
                  AND edge_type = :edge_type
                LIMIT 1
                """)
            params: dict[str, Any] = {
                "from_node": from_node,
                "to_node": to_node,
                "edge_type": edge_type,
            }
        else:
            sql = text("""
                SELECT id::text, from_node::text, to_node::text,
                       edge_type, weight, origin, co_access_count, last_reinforced
                FROM mesh_edges
                WHERE from_node = :from_node::uuid
                  AND to_node   = :to_node::uuid
                LIMIT 1
                """)
            params = {"from_node": from_node, "to_node": to_node}

        async with self.engine.connect() as conn:
            row = await conn.execute(sql, params)
            result = row.mappings().fetchone()
        return dict(result) if result else None

    async def update_edge(
        self,
        edge_id: str,
        weight: float | None = None,
        co_access_count: int | None = None,
        edge_type: str | None = None,
        origin: str | None = None,
    ) -> None:
        """Partially update an edge's mutable fields (#2055, #2117).

        Supports weight, co_access_count (EdgeLearner) and edge_type, origin
        (EdgeDiscoverer) in a single generic method.
        """
        updates: list[str] = ["last_reinforced = NOW()"]
        params: dict[str, Any] = {"edge_id": edge_id}
        if weight is not None:
            updates.append("weight = :weight")
            params["weight"] = weight
        if co_access_count is not None:
            updates.append("co_access_count = :co_access_count")
            params["co_access_count"] = co_access_count
        if edge_type is not None:
            updates.append("edge_type = :edge_type")
            params["edge_type"] = edge_type
        if origin is not None:
            updates.append("origin = :origin")
            params["origin"] = origin
        sql = text(f"UPDATE mesh_edges SET {', '.join(updates)} WHERE id = :edge_id::uuid")
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
        sql = text("""
            SELECT e.id::text        AS edge_id,
                   e.to_node::text   AS neighbor_id,
                   e.edge_type,
                   e.weight,
                   e.origin
            FROM mesh_edges e
            WHERE e.from_node = :node_id::uuid
              AND e.weight    >= :min_weight
            ORDER BY e.weight DESC
            """)
        async with self.engine.connect() as conn:
            rows = await conn.execute(sql, {"node_id": node_id, "min_weight": min_weight})
            return [dict(r) for r in rows.mappings()]

    async def get_anchor_neighbors(self, seed_ids: list[str]) -> list[str]:
        """Return IDs of anchor nodes adjacent to any seed_id. Satisfies _AnchorDB Protocol (#4819)."""
        if not seed_ids:
            return []
        sql = text("""
            SELECT DISTINCT n.id::text
            FROM mesh_nodes n
            JOIN mesh_edges e
              ON e.from_node = n.id OR e.to_node = n.id
            WHERE (e.from_node = ANY(:seeds::uuid[])
               OR  e.to_node   = ANY(:seeds::uuid[]))
              AND n.is_anchor = TRUE
              AND n.id != ALL(:seeds::uuid[])
            """)
        async with self.engine.connect() as conn:
            rows = await conn.execute(sql, {"seeds": seed_ids})
            return [row["id"] for row in rows.mappings()]

    async def fetch_candidate_edges(
        self,
        edge_type: str,
        min_weight: float,
        min_co_access: int,
        origin: str,
        limit: int,
    ) -> list[dict]:
        """Return high-weight, well-travelled edges for EdgeDiscoverer (#2117).

        Joins mesh_edges with mesh_nodes to include from_content/to_content so
        the LLM can read the chunk text when naming the relationship.
        """
        sql = text("""
            SELECT e.id::text          AS id,
                   e.from_node::text   AS from_node,
                   e.to_node::text     AS to_node,
                   e.edge_type,
                   e.weight,
                   e.origin,
                   e.co_access_count,
                   fn.chunk_id         AS from_chunk_id,
                   tn.chunk_id         AS to_chunk_id
            FROM mesh_edges e
            JOIN mesh_nodes fn ON fn.id = e.from_node
            JOIN mesh_nodes tn ON tn.id = e.to_node
            WHERE e.edge_type      = :edge_type
              AND e.weight         >= :min_weight
              AND e.co_access_count >= :min_co_access
              AND e.origin         = :origin
            ORDER BY e.weight DESC
            LIMIT :limit
            """)
        params: dict[str, Any] = {
            "edge_type": edge_type,
            "min_weight": min_weight,
            "min_co_access": min_co_access,
            "origin": origin,
            "limit": limit,
        }
        async with self.engine.connect() as conn:
            rows = await conn.execute(sql, params)
            return [dict(r) for r in rows.mappings()]

    async def fetch_edges(self, min_weight: float = 0.5) -> list[dict]:
        """Return all edges above min_weight. Satisfies MeshEdgeSync Protocol (#2029, #2055)."""
        sql = text("""
            SELECT id::text, from_node::text, to_node::text,
                   edge_type, weight, origin
            FROM mesh_edges
            WHERE weight >= :min_weight
            ORDER BY weight DESC
            """)
        async with self.engine.connect() as conn:
            rows = await conn.execute(sql, {"min_weight": min_weight})
            return [dict(r) for r in rows.mappings()]

    async def get_co_access_count(self, node_a: str, node_b: str) -> int:
        """Return the co_access_count for the edge between node_a and node_b (#2055)."""
        sql = text("""
            SELECT COALESCE(co_access_count, 0)
            FROM mesh_edges
            WHERE from_node = :node_a::uuid
              AND to_node   = :node_b::uuid
            LIMIT 1
            """)
        async with self.engine.connect() as conn:
            row = await conn.execute(sql, {"node_a": node_a, "node_b": node_b})
            return row.scalar() or 0

    # ------------------------------------------------------------------
    # MeshPruner operations
    # ------------------------------------------------------------------

    async def decay_edges(
        self,
        origins: list[str],
        not_reinforced_since: datetime,
        decay_factor: float,
    ) -> int:
        """Multiply weight by decay_factor for matching edges. Returns count affected (#2178)."""
        sql = text("""
            UPDATE mesh_edges
            SET weight = weight * :factor,
                last_reinforced = NOW()
            WHERE origin = ANY(:origins)
              AND (last_reinforced IS NULL OR last_reinforced < :cutoff)
            """)
        async with self.engine.begin() as conn:
            result = await conn.execute(
                sql,
                {
                    "factor": decay_factor,
                    "origins": origins,
                    "cutoff": not_reinforced_since,
                },
            )
        logger.debug("Decayed %d edges factor=%.3f", result.rowcount, decay_factor)
        return result.rowcount

    async def delete_edges(self, max_weight: float) -> int:
        """Delete edges at or below max_weight. Returns count deleted (#2178)."""
        sql = text("DELETE FROM mesh_edges WHERE weight <= :max_weight")
        async with self.engine.begin() as conn:
            result = await conn.execute(sql, {"max_weight": max_weight})
        logger.debug("Deleted %d edges at or below weight=%.3f", result.rowcount, max_weight)
        return result.rowcount

    async def archive_orphan_nodes(self, no_access_since: datetime) -> int:
        """Archive nodes with no edges and no access since cutoff. Returns count (#2178)."""
        sql = text("""
            WITH archived AS (
                DELETE FROM mesh_nodes n
                WHERE (last_accessed IS NULL OR last_accessed < :cutoff)
                  AND NOT EXISTS (
                      SELECT 1 FROM mesh_edges e
                      WHERE e.from_node = n.id OR e.to_node = n.id
                  )
                RETURNING n.*
            )
            INSERT INTO mesh_nodes_archive
            SELECT * FROM archived
            ON CONFLICT DO NOTHING
            """)
        async with self.engine.begin() as conn:
            result = await conn.execute(sql, {"cutoff": no_access_since})
        logger.debug("Archived %d orphan nodes", result.rowcount)
        return result.rowcount

    async def merge_duplicate_edges(self) -> int:
        """Merge edges with same from/to but different types; keep highest weight (#2178)."""
        sql = text("""
            WITH ranked AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY from_node, to_node
                           ORDER BY weight DESC
                       ) AS rn
                FROM mesh_edges
            ),
            deleted AS (
                DELETE FROM mesh_edges
                WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
                RETURNING id
            )
            SELECT COUNT(*) FROM deleted
            """)
        async with self.engine.begin() as conn:
            result = await conn.execute(sql)
            count = result.scalar() or 0
        logger.debug("Merged %d duplicate edges", count)
        return count

    async def get_graph_density(self) -> float:
        """Return avg edges per node (#2178)."""
        sql = text("""
            SELECT CASE WHEN COUNT(DISTINCT n.id) = 0 THEN 0.0
                        ELSE COUNT(e.id)::float / COUNT(DISTINCT n.id)
                   END
            FROM mesh_nodes n
            LEFT JOIN mesh_edges e ON e.from_node = n.id
            """)
        async with self.engine.connect() as conn:
            result = await conn.execute(sql)
            return float(result.scalar() or 0.0)

    # ------------------------------------------------------------------
    # NodePromoter operations
    # ------------------------------------------------------------------

    async def get_promotion_candidates(self, min_access: int, min_edges: int) -> list[dict]:
        """Return nodes with access_count >= min_access, edge_count >= min_edges, not anchor (#2178)."""
        sql = text("""
            SELECT n.id::text,
                   n.chunk_id,
                   n.node_type,
                   n.access_count,
                   COUNT(e.id) AS edge_count
            FROM mesh_nodes n
            LEFT JOIN mesh_edges e ON e.from_node = n.id
            WHERE n.is_anchor = FALSE
              AND n.access_count >= :min_access
            GROUP BY n.id
            HAVING COUNT(e.id) >= :min_edges
            """)
        async with self.engine.connect() as conn:
            rows = await conn.execute(sql, {"min_access": min_access, "min_edges": min_edges})
            return [dict(r) for r in rows.mappings()]

    async def get_stale_anchors(self, max_access: int, inactive_days: int) -> list[dict]:
        """Return anchor nodes with access below threshold, inactive for N days (#2178)."""
        sql = text("""
            SELECT id::text, chunk_id, node_type, access_count, last_accessed
            FROM mesh_nodes
            WHERE is_anchor = TRUE
              AND access_count <= :max_access
              AND (last_accessed IS NULL
                   OR last_accessed < NOW() - make_interval(days => :inactive_days))
            """)
        async with self.engine.connect() as conn:
            rows = await conn.execute(sql, {"max_access": max_access, "inactive_days": inactive_days})
            return [dict(r) for r in rows.mappings()]

    async def get_neighborhood(self, node_id: str, hops: int) -> list[dict]:
        """BFS to collect nodes within N hops. Returns list of dicts with content (#2178)."""
        sql = text("""
            WITH RECURSIVE bfs AS (
                SELECT id, 0 AS depth
                FROM mesh_nodes
                WHERE id = :node_id::uuid
                UNION
                SELECT e.to_node, b.depth + 1
                FROM bfs b
                JOIN mesh_edges e ON e.from_node = b.id
                WHERE b.depth < :hops
            )
            SELECT DISTINCT n.id::text, n.chunk_id, n.node_type, n.raptor_level
            FROM bfs b
            JOIN mesh_nodes n ON n.id = b.id
            """)
        async with self.engine.connect() as conn:
            rows = await conn.execute(sql, {"node_id": node_id, "hops": hops})
            return [dict(r) for r in rows.mappings()]

    async def promote_to_anchor(self, node_id: str) -> None:
        """Set is_anchor=True for node_id (#2178)."""
        sql = text("UPDATE mesh_nodes SET is_anchor = TRUE WHERE id = :node_id::uuid")
        async with self.engine.begin() as conn:
            await conn.execute(sql, {"node_id": node_id})
        logger.info("Promoted node %s to anchor", node_id)

    async def demote_anchor(self, node_id: str) -> None:
        """Set is_anchor=False for node_id (#2178)."""
        sql = text("UPDATE mesh_nodes SET is_anchor = FALSE WHERE id = :node_id::uuid")
        async with self.engine.begin() as conn:
            await conn.execute(sql, {"node_id": node_id})
        logger.info("Demoted anchor node %s", node_id)

    # ------------------------------------------------------------------
    # Evolution log
    # ------------------------------------------------------------------

    async def log_evolution(
        self,
        event_type: str,
        entity_id: str | None,
        old_value: dict | None,
        new_value: dict | None,
        actor: str,
    ) -> None:
        """Append an audit entry to mesh_evolution_log (#2055)."""
        sql = text("""
            INSERT INTO mesh_evolution_log
                (event_type, entity_id, old_value, new_value, actor)
            VALUES
                (:event_type,
                 :entity_id::uuid,
                 :old_value::jsonb,
                 :new_value::jsonb,
                 :actor)
            """)
        import json

        async with self.engine.begin() as conn:
            await conn.execute(
                sql,
                {
                    "event_type": event_type,
                    "entity_id": entity_id,
                    "old_value": (json.dumps(old_value) if old_value is not None else None),
                    "new_value": (json.dumps(new_value) if new_value is not None else None),
                    "actor": actor,
                },
            )
        logger.debug("Logged evolution event %s entity=%s", event_type, entity_id)
