# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for MeshSeeder loader.

Issue #2028: MeshSeeder loader for graph edge creation (Neural Mesh RAG Phase 2).
"""

from typing import Any, List
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from knowledge.pipeline.base import PipelineContext
from knowledge.pipeline.loaders.mesh_seeder import MeshSeeder
from knowledge.pipeline.models.chunk import ProcessedChunk
from knowledge.pipeline.models.entity import Entity
from knowledge.pipeline.models.relationship import Relationship

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chunk(doc_id: Any, chunk_index: int, source_file: str) -> ProcessedChunk:
    """Create a ProcessedChunk with a source_file in metadata."""
    return ProcessedChunk(
        content=f"chunk content {chunk_index}",
        document_id=doc_id,
        chunk_index=chunk_index,
        metadata={"source_file": source_file},
    )


def _make_entity(doc_id: Any, chunk_ids: List[Any], name: str = "Python") -> Entity:
    """Create an Entity referencing specified chunk IDs."""
    return Entity(
        name=name,
        canonical_name=name.lower(),
        entity_type="TECHNOLOGY",
        source_document_id=doc_id,
        source_chunk_ids=chunk_ids,
    )


def _make_relationship(src_id: Any, tgt_id: Any) -> Relationship:
    """Create a Relationship between two entity IDs."""
    return Relationship(
        source_entity_id=src_id,
        target_entity_id=tgt_id,
        relationship_type="USES",
    )


def _context_with(chunks=None, entities=None, relationships=None) -> PipelineContext:
    """Build a PipelineContext pre-populated with the given data."""
    ctx = PipelineContext()
    ctx.chunks = chunks or []
    ctx.entities = entities or []
    ctx.relationships = relationships or []
    return ctx


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMeshSeederPartOfEdges:
    """PART_OF edge generation — chunks sharing a source file."""

    @pytest.mark.asyncio
    async def test_two_chunks_same_file_yields_one_part_of_edge(self):
        doc_id = uuid4()
        chunks = [
            _make_chunk(doc_id, 0, "file_a.txt"),
            _make_chunk(doc_id, 1, "file_a.txt"),
        ]
        seeder = MeshSeeder()
        nodes = seeder._build_node_list(chunks)
        edges = seeder._build_part_of_edges(nodes)

        assert len(edges) == 1
        assert edges[0]["edge_type"] == "PART_OF"

    @pytest.mark.asyncio
    async def test_different_files_produce_no_part_of_edges(self):
        doc_id = uuid4()
        chunks = [
            _make_chunk(doc_id, 0, "file_a.txt"),
            _make_chunk(doc_id, 1, "file_b.txt"),
        ]
        seeder = MeshSeeder()
        nodes = seeder._build_node_list(chunks)
        edges = seeder._build_part_of_edges(nodes)

        assert edges == []


class TestMeshSeederSequenceEdges:
    """NEXT edge generation — sequential chunks within a file."""

    @pytest.mark.asyncio
    async def test_three_sequential_chunks_yield_two_next_edges(self):
        doc_id = uuid4()
        chunks = [
            _make_chunk(doc_id, 0, "doc.md"),
            _make_chunk(doc_id, 1, "doc.md"),
            _make_chunk(doc_id, 2, "doc.md"),
        ]
        seeder = MeshSeeder()
        nodes = seeder._build_node_list(chunks)
        edges = seeder._build_sequence_edges(nodes)

        assert len(edges) == 2
        assert all(e["edge_type"] == "NEXT" for e in edges)

    @pytest.mark.asyncio
    async def test_sequence_edge_order_follows_chunk_index(self):
        doc_id = uuid4()
        # Intentionally out-of-order to verify sort
        chunks = [
            _make_chunk(doc_id, 2, "doc.md"),
            _make_chunk(doc_id, 0, "doc.md"),
            _make_chunk(doc_id, 1, "doc.md"),
        ]
        seeder = MeshSeeder()
        nodes = seeder._build_node_list(chunks)
        edges = seeder._build_sequence_edges(nodes)

        # from_node of second edge must be the to_node of first edge
        assert edges[0]["to_node"] == edges[1]["from_node"]


class TestMeshSeederEntityEdges:
    """SHARED_ENTITY edge generation."""

    @pytest.mark.asyncio
    async def test_two_chunks_sharing_entity_yield_one_shared_entity_edge(self):
        doc_id = uuid4()
        chunks = [
            _make_chunk(doc_id, 0, "doc.md"),
            _make_chunk(doc_id, 1, "doc.md"),
        ]
        entity = _make_entity(doc_id, [chunks[0].id, chunks[1].id])
        seeder = MeshSeeder()
        nodes = seeder._build_node_list(chunks)
        edges = seeder._build_entity_edges(nodes, [entity])

        assert len(edges) == 1
        assert edges[0]["edge_type"] == "SHARED_ENTITY"
        assert edges[0]["weight"] == 0.8

    @pytest.mark.asyncio
    async def test_duplicate_entity_pairs_deduplicated(self):
        doc_id = uuid4()
        chunks = [
            _make_chunk(doc_id, 0, "doc.md"),
            _make_chunk(doc_id, 1, "doc.md"),
        ]
        # Two entities both reference the same chunk pair
        entity_a = _make_entity(doc_id, [chunks[0].id, chunks[1].id], "Python")
        entity_b = _make_entity(doc_id, [chunks[0].id, chunks[1].id], "Python")
        seeder = MeshSeeder()
        nodes = seeder._build_node_list(chunks)
        edges = seeder._build_entity_edges(nodes, [entity_a, entity_b])

        assert len(edges) == 1


class TestMeshSeederSingleChunk:
    """Edge generation with a single chunk — no edges expected."""

    @pytest.mark.asyncio
    async def test_single_chunk_produces_no_edges(self):
        doc_id = uuid4()
        chunks = [_make_chunk(doc_id, 0, "solo.txt")]
        seeder = MeshSeeder()
        result = await seeder.load(_context_with(chunks=chunks))

        assert result["nodes_created"] == 1
        assert result["edges_created"] == 0


class TestMeshSeederPersistence:
    """Persistence — db.create_edge is called for each edge."""

    @pytest.mark.asyncio
    async def test_db_create_edge_called_for_each_edge(self):
        doc_id = uuid4()
        chunks = [
            _make_chunk(doc_id, 0, "file.py"),
            _make_chunk(doc_id, 1, "file.py"),
        ]
        mock_db = AsyncMock()
        seeder = MeshSeeder(db=mock_db)
        result = await seeder.load(_context_with(chunks=chunks))

        assert mock_db.create_edge.call_count == result["edges_created"]

    @pytest.mark.asyncio
    async def test_no_db_does_not_raise(self):
        doc_id = uuid4()
        chunks = [_make_chunk(doc_id, 0, "file.py")]
        seeder = MeshSeeder(db=None)
        result = await seeder.load(_context_with(chunks=chunks))

        assert result["nodes_created"] == 1


class TestMeshSeederRelationshipEdges:
    """Typed relationship edges from ECL-extracted relationships."""

    @pytest.mark.asyncio
    async def test_relationship_edges_preserve_type(self):
        src_id = uuid4()
        tgt_id = uuid4()
        rel = _make_relationship(src_id, tgt_id)
        seeder = MeshSeeder()
        edges = seeder._build_relationship_edges([rel])

        assert len(edges) == 1
        assert edges[0]["edge_type"] == "USES"
        assert edges[0]["from_node"] == str(src_id)
        assert edges[0]["to_node"] == str(tgt_id)
        assert edges[0]["weight"] == 0.9


class TestMeshSeederSimilarToEdges:
    """SIMILAR_TO edge generation via cosine similarity of embeddings (#2049)."""

    def _make_nodes(self, n: int) -> List[Any]:
        """Return n minimal node dicts."""
        return [{"id": f"n_{i}"} for i in range(n)]

    def test_none_embeddings_returns_empty(self):
        seeder = MeshSeeder()
        nodes = self._make_nodes(3)
        assert seeder._build_similar_to_edges(nodes, None) == []

    def test_single_embedding_returns_empty(self):
        import numpy as np

        seeder = MeshSeeder()
        nodes = self._make_nodes(1)
        embeddings = np.array([[1.0, 0.0]])
        assert seeder._build_similar_to_edges(nodes, embeddings) == []

    def test_identical_embeddings_produce_similar_to_edge(self):
        import numpy as np

        seeder = MeshSeeder(similarity_threshold=0.82)
        nodes = self._make_nodes(2)
        # Identical unit vectors → cosine similarity == 1.0
        embeddings = np.array([[1.0, 0.0], [1.0, 0.0]])
        edges = seeder._build_similar_to_edges(nodes, embeddings)

        assert len(edges) == 1
        assert edges[0]["edge_type"] == "SIMILAR_TO"
        assert edges[0]["from_node"] == "n_0"
        assert edges[0]["to_node"] == "n_1"
        assert abs(edges[0]["weight"] - 1.0) < 1e-6

    def test_orthogonal_embeddings_produce_no_edge(self):
        import numpy as np

        seeder = MeshSeeder(similarity_threshold=0.82)
        nodes = self._make_nodes(2)
        # Orthogonal vectors → cosine similarity == 0.0
        embeddings = np.array([[1.0, 0.0], [0.0, 1.0]])
        edges = seeder._build_similar_to_edges(nodes, embeddings)

        assert edges == []

    def test_threshold_boundary_excluded(self):
        """Pairs strictly below threshold must be excluded."""
        import numpy as np

        seeder = MeshSeeder(similarity_threshold=0.90)
        nodes = self._make_nodes(2)
        # cosine similarity ≈ 0.8 < 0.90
        embeddings = np.array([[1.0, 0.0], [0.6, 0.8]])
        edges = seeder._build_similar_to_edges(nodes, embeddings)

        assert edges == []

    def test_threshold_boundary_included(self):
        """Pairs at exactly the threshold must be included."""
        import numpy as np

        seeder = MeshSeeder(similarity_threshold=0.6)
        nodes = self._make_nodes(2)
        # cosine similarity == 0.6
        embeddings = np.array([[1.0, 0.0], [0.6, 0.8]])
        edges = seeder._build_similar_to_edges(nodes, embeddings)

        assert len(edges) == 1

    def test_zero_vector_handled_without_division_error(self):
        """A zero-norm embedding must not raise ZeroDivisionError."""
        import numpy as np

        seeder = MeshSeeder(similarity_threshold=0.5)
        nodes = self._make_nodes(2)
        embeddings = np.array([[0.0, 0.0], [1.0, 0.0]])
        # Should not raise; similarity to zero vector is 0.0
        edges = seeder._build_similar_to_edges(nodes, embeddings)
        assert isinstance(edges, list)

    @pytest.mark.asyncio
    async def test_load_wires_similar_to_edges_from_context_metadata(self):
        """Embeddings in context.metadata['embeddings'] flow into SIMILAR_TO edges."""
        from uuid import uuid4

        import numpy as np

        doc_id = uuid4()
        chunks = [
            _make_chunk(doc_id, 0, "a.txt"),
            _make_chunk(doc_id, 1, "a.txt"),
        ]
        ctx = _context_with(chunks=chunks)
        # Identical embeddings → similarity == 1.0 > default threshold 0.82
        ctx.metadata["embeddings"] = np.array([[1.0, 0.0], [1.0, 0.0]])

        seeder = MeshSeeder()
        # Without embeddings: 1 PART_OF + 1 NEXT = 2. With identical embeddings: +1 SIMILAR_TO.
        result_without = await seeder.load(_context_with(chunks=chunks))
        result_with = await seeder.load(ctx)

        assert result_with["edges_created"] > result_without["edges_created"]
