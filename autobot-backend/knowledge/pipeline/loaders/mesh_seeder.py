# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
MeshSeeder — creates structural and semantic edges in the mesh graph (#1994, #2028).

Part of Neural Mesh RAG Phase 2, Task 2.4.
"""

from itertools import combinations
from typing import Any, Dict, List, Tuple

import numpy as np

from autobot_shared.logging_manager import get_logger
from knowledge.pipeline.base import BaseLoader, PipelineContext
from knowledge.pipeline.registry import TaskRegistry

logger = get_logger(__name__)

_EdgeDict = Dict[str, Any]


@TaskRegistry.register_loader("mesh_seeder")
class MeshSeeder(BaseLoader):
    """Seeds the mesh graph with structural, entity-based, and typed relationship edges."""

    def __init__(self, db: Any | None = None, similarity_threshold: float = 0.82) -> None:
        """
        Initialize MeshSeeder.

        Args:
            db: Async graph database client exposing create_edge(**edge_dict).
            similarity_threshold: Cosine similarity cutoff for SIMILAR_TO edges.
        """
        self.db = db
        self.similarity_threshold = similarity_threshold

    async def load(self, context: PipelineContext) -> Dict[str, int]:
        """
        Build and persist mesh edges from pipeline context.

        Args:
            context: Pipeline context populated by extractors and cognifiers.

        Returns:
            Dict with counts: nodes_created, edges_created.
        """
        chunks = context.chunks or []
        entities = context.entities or []
        relationships = context.relationships or []
        embeddings: np.ndarray | None = context.metadata.get("embeddings")

        nodes = self._build_node_list(chunks)
        edges: List[_EdgeDict] = []
        edges.extend(self._build_part_of_edges(nodes))
        edges.extend(self._build_sequence_edges(nodes))
        if entities:
            edges.extend(self._build_entity_edges(nodes, entities))
        if relationships:
            edges.extend(self._build_relationship_edges(relationships))
        edges.extend(self._build_similar_to_edges(nodes, embeddings))

        if self.db:
            await self._persist_edges(edges)

        logger.info(
            "MeshSeeder: %s nodes, %s edges created (#2028)",
            len(nodes),
            len(edges),
        )
        return {"nodes_created": len(nodes), "edges_created": len(edges)}

    # ------------------------------------------------------------------
    # Node builder
    # ------------------------------------------------------------------

    def _build_node_list(self, chunks: List[Any]) -> List[Dict[str, Any]]:
        """Map pipeline chunks to lightweight node dicts for edge construction.

        node["id"] equals node["chunk_id"] — both use the canonical chunk UUID
        so that entity edges (which carry source_chunk_ids UUIDs) reference the
        same ID space as structural edges (#2050).
        """
        return [
            {
                "id": str(getattr(c, "id", f"chunk_{i}")),
                "chunk_id": str(getattr(c, "id", f"chunk_{i}")),
                "source_file": getattr(c, "metadata", {}).get("source_file", ""),
                "chunk_index": getattr(c, "chunk_index", i),
            }
            for i, c in enumerate(chunks)
        ]

    # ------------------------------------------------------------------
    # Edge builders
    # ------------------------------------------------------------------

    def _group_nodes_by_file(self, nodes: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Return nodes grouped by source_file, omitting nodes without a file."""
        by_file: Dict[str, List[Dict[str, Any]]] = {}
        for n in nodes:
            source_file = n.get("source_file")
            if source_file:
                by_file.setdefault(source_file, []).append(n)
        return by_file

    def _build_part_of_edges(self, nodes: List[Dict[str, Any]]) -> List[_EdgeDict]:
        """Create PART_OF edges between all chunks sharing the same source file."""
        edges: List[_EdgeDict] = []
        for file_nodes in self._group_nodes_by_file(nodes).values():
            for a, b in combinations(file_nodes, 2):
                edges.append(
                    {
                        "from_node": a["id"],
                        "to_node": b["id"],
                        "edge_type": "PART_OF",
                        "origin": "seeder",
                        "weight": 1.0,
                    }
                )
        return edges

    def _build_sequence_edges(self, nodes: List[Dict[str, Any]]) -> List[_EdgeDict]:
        """Create NEXT edges between adjacent chunks within the same source file."""
        edges: List[_EdgeDict] = []
        for file_nodes in self._group_nodes_by_file(nodes).values():
            sorted_nodes = sorted(file_nodes, key=lambda x: x.get("chunk_index", 0))
            for i in range(len(sorted_nodes) - 1):
                edges.append(
                    {
                        "from_node": sorted_nodes[i]["id"],
                        "to_node": sorted_nodes[i + 1]["id"],
                        "edge_type": "NEXT",
                        "origin": "seeder",
                        "weight": 1.0,
                    }
                )
        return edges

    def _build_entity_edges(self, nodes: List[Dict[str, Any]], entities: List[Any]) -> List[_EdgeDict]:
        """Create SHARED_ENTITY edges between chunk-pairs that mention the same entity.

        Uses a node_ids set to restrict edges to chunks present in the current
        node list, preventing dangling references to unknown IDs (#2050).
        """
        node_ids = {n["id"] for n in nodes}
        entity_to_chunks = self._map_entity_to_chunks(entities)
        edges: List[_EdgeDict] = []
        seen: set = set()
        for chunk_ids in entity_to_chunks.values():
            valid = sorted(cid for cid in chunk_ids if cid in node_ids)
            for a, b in combinations(valid, 2):
                key: Tuple[str, str] = (a, b)
                if key not in seen:
                    seen.add(key)
                    edges.append(
                        {
                            "from_node": a,
                            "to_node": b,
                            "edge_type": "SHARED_ENTITY",
                            "origin": "seeder",
                            "weight": 0.8,
                        }
                    )
        return edges

    def _map_entity_to_chunks(self, entities: List[Any]) -> Dict[str, set]:
        """Return a mapping from canonical entity name to set of chunk id strings."""
        entity_chunks: Dict[str, set] = {}
        for e in entities:
            canonical = getattr(e, "canonical_name", getattr(e, "name", "")).lower()
            for cid in getattr(e, "source_chunk_ids", []):
                entity_chunks.setdefault(canonical, set()).add(str(cid))
        return entity_chunks

    def _build_relationship_edges(self, relationships: List[Any]) -> List[_EdgeDict]:
        """Create typed edges from ECL-extracted entity relationships."""
        return [
            {
                "from_node": str(getattr(r, "source_entity_id", "")),
                "to_node": str(getattr(r, "target_entity_id", "")),
                "edge_type": str(getattr(r, "relationship_type", "RELATES_TO")),
                "origin": "seeder",
                "weight": 0.9,
            }
            for r in relationships
        ]

    def _compute_cosine_similarity(self, embeddings: np.ndarray) -> np.ndarray:
        """Return pairwise cosine similarity matrix for the given embedding array (#2049)."""
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        normalized = embeddings / norms
        return normalized @ normalized.T

    def _build_similar_to_edges(
        self,
        nodes: List[Dict[str, Any]],
        embeddings: np.ndarray | None = None,
    ) -> List[_EdgeDict]:
        """Create SIMILAR_TO edges for chunk pairs with cosine similarity >= threshold (#2049)."""
        if embeddings is None or len(embeddings) < 2:
            return []
        similarity_matrix = self._compute_cosine_similarity(embeddings)
        # Vectorized extraction of above-threshold pairs (#2081)
        upper = np.triu(similarity_matrix, k=1)
        rows, cols = np.where(upper >= self.similarity_threshold)
        return [
            {
                "from_node": nodes[int(r)]["id"],
                "to_node": nodes[int(c)]["id"],
                "edge_type": "SIMILAR_TO",
                "origin": "seeder",
                "weight": float(upper[r, c]),
            }
            for r, c in zip(rows, cols)
        ]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def _persist_edges(self, edges: List[_EdgeDict]) -> None:
        """Write all edges to the graph database via db.create_edge."""
        for edge in edges:
            await self.db.create_edge(**edge)
        logger.info("MeshSeeder: persisted %s edges to graph db (#2028)", len(edges))
