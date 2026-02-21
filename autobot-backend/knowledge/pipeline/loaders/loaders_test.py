# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for pipeline loaders with mocked backends.

Issue #1075: Test coverage for ChromaDB, Redis Graph, and SQLite loaders.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from backend.knowledge.pipeline.base import PipelineContext
from backend.knowledge.pipeline.models.chunk import ProcessedChunk
from backend.knowledge.pipeline.models.entity import Entity
from backend.knowledge.pipeline.models.event import TemporalEvent
from backend.knowledge.pipeline.models.relationship import Relationship
from backend.knowledge.pipeline.models.summary import Summary

# --- Fixtures ---


@pytest.fixture
def context_with_data():
    """Pipeline context populated with test data."""
    ctx = PipelineContext()
    doc_id = uuid4()
    ctx.document_id = doc_id

    chunk = ProcessedChunk(
        content="Test chunk",
        document_id=doc_id,
        chunk_index=0,
    )
    ctx.chunks = [chunk]

    entity = Entity(
        name="Python",
        canonical_name="python",
        entity_type="TECHNOLOGY",
        source_document_id=doc_id,
        source_chunk_ids=[chunk.id],
    )
    ctx.entities = [entity]

    rel = Relationship(
        source_entity_id=entity.id,
        target_entity_id=uuid4(),
        relationship_type="USES",
        source_chunk_ids=[chunk.id],
    )
    ctx.relationships = [rel]

    event = TemporalEvent(
        name="Release",
        source_document_id=doc_id,
        source_chunk_ids=[chunk.id],
    )
    ctx.events = [event]

    summary = Summary(
        content="A test summary",
        level="chunk",
        source_document_id=doc_id,
        source_chunk_ids=[chunk.id],
    )
    ctx.summaries = [summary]

    return ctx


# --- ChromaDB Loader Tests ---


class TestChromaDBLoader:
    """Tests for ChromaDBLoader with mocked ChromaDB client."""

    @pytest.mark.asyncio
    async def test_load_chunks(self, context_with_data):
        mock_collection = AsyncMock()
        mock_client = AsyncMock()
        mock_client.get_or_create_collection.return_value = mock_collection

        with patch(
            "backend.knowledge.pipeline.loaders.chromadb_loader."
            "get_async_chromadb_client",
            return_value=mock_client,
        ):
            from backend.knowledge.pipeline.loaders.chromadb_loader import (
                ChromaDBLoader,
            )

            loader = ChromaDBLoader()
            await loader.load(context_with_data)

        mock_collection.upsert.assert_called()

    @pytest.mark.asyncio
    async def test_load_with_summaries(self, context_with_data):
        mock_collection = AsyncMock()
        mock_client = AsyncMock()
        mock_client.get_or_create_collection.return_value = mock_collection

        with patch(
            "backend.knowledge.pipeline.loaders.chromadb_loader."
            "get_async_chromadb_client",
            return_value=mock_client,
        ):
            from backend.knowledge.pipeline.loaders.chromadb_loader import (
                ChromaDBLoader,
            )

            loader = ChromaDBLoader(load_summaries=True)
            await loader.load(context_with_data)

        assert mock_collection.upsert.call_count == 2

    @pytest.mark.asyncio
    async def test_no_summaries_when_disabled(self, context_with_data):
        mock_collection = AsyncMock()
        mock_client = AsyncMock()
        mock_client.get_or_create_collection.return_value = mock_collection

        with patch(
            "backend.knowledge.pipeline.loaders.chromadb_loader."
            "get_async_chromadb_client",
            return_value=mock_client,
        ):
            from backend.knowledge.pipeline.loaders.chromadb_loader import (
                ChromaDBLoader,
            )

            loader = ChromaDBLoader(load_summaries=False)
            await loader.load(context_with_data)

        assert mock_collection.upsert.call_count == 1

    @pytest.mark.asyncio
    async def test_empty_context_no_upsert(self):
        mock_client = AsyncMock()

        with patch(
            "backend.knowledge.pipeline.loaders.chromadb_loader."
            "get_async_chromadb_client",
            return_value=mock_client,
        ):
            from backend.knowledge.pipeline.loaders.chromadb_loader import (
                ChromaDBLoader,
            )

            ctx = PipelineContext()
            loader = ChromaDBLoader()
            await loader.load(ctx)

        mock_client.get_or_create_collection.assert_not_called()


# --- Redis Graph Loader Tests ---


class TestRedisGraphLoader:
    """Tests for RedisGraphLoader with mocked Redis client."""

    @pytest.mark.asyncio
    async def test_load_entities(self, context_with_data):
        mock_redis = MagicMock()
        mock_json = MagicMock()
        mock_redis.json.return_value = mock_json

        with patch(
            "backend.knowledge.pipeline.loaders.redis_graph_loader." "get_redis_client",
            return_value=mock_redis,
        ):
            from backend.knowledge.pipeline.loaders.redis_graph_loader import (
                RedisGraphLoader,
            )

            loader = RedisGraphLoader()
            await loader.load(context_with_data)

        mock_json.set.assert_called()
        mock_redis.set.assert_called()

    @pytest.mark.asyncio
    async def test_load_relationships(self, context_with_data):
        mock_redis = MagicMock()
        mock_json = MagicMock()
        mock_redis.json.return_value = mock_json

        with patch(
            "backend.knowledge.pipeline.loaders.redis_graph_loader." "get_redis_client",
            return_value=mock_redis,
        ):
            from backend.knowledge.pipeline.loaders.redis_graph_loader import (
                RedisGraphLoader,
            )

            loader = RedisGraphLoader()
            await loader.load(context_with_data)

        mock_redis.sadd.assert_called()

    @pytest.mark.asyncio
    async def test_load_events_with_timeline(self, context_with_data):
        from datetime import datetime

        context_with_data.events[0].timestamp = datetime(2024, 6, 1)

        mock_redis = MagicMock()
        mock_json = MagicMock()
        mock_redis.json.return_value = mock_json

        with patch(
            "backend.knowledge.pipeline.loaders.redis_graph_loader." "get_redis_client",
            return_value=mock_redis,
        ):
            from backend.knowledge.pipeline.loaders.redis_graph_loader import (
                RedisGraphLoader,
            )

            loader = RedisGraphLoader()
            await loader.load(context_with_data)

        mock_redis.zadd.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_context_no_writes(self):
        mock_redis = MagicMock()

        with patch(
            "backend.knowledge.pipeline.loaders.redis_graph_loader." "get_redis_client",
            return_value=mock_redis,
        ):
            from backend.knowledge.pipeline.loaders.redis_graph_loader import (
                RedisGraphLoader,
            )

            ctx = PipelineContext()
            loader = RedisGraphLoader()
            await loader.load(ctx)

        mock_redis.json.assert_not_called()

    @pytest.mark.asyncio
    async def test_bidirectional_index(self, context_with_data):
        context_with_data.relationships[0].bidirectional = True

        mock_redis = MagicMock()
        mock_json = MagicMock()
        mock_redis.json.return_value = mock_json

        with patch(
            "backend.knowledge.pipeline.loaders.redis_graph_loader." "get_redis_client",
            return_value=mock_redis,
        ):
            from backend.knowledge.pipeline.loaders.redis_graph_loader import (
                RedisGraphLoader,
            )

            loader = RedisGraphLoader()
            await loader.load(context_with_data)

        reverse_calls = [c for c in mock_json.set.call_args_list if "reverse" in str(c)]
        assert len(reverse_calls) > 0


# --- SQLite Loader Tests ---


class TestSQLiteLoader:
    """Tests for SQLiteLoader with temp database."""

    @pytest.mark.asyncio
    async def test_load_creates_tables(self, context_with_data, tmp_path):
        from backend.knowledge.pipeline.loaders.sqlite_loader import SQLiteLoader

        db_path = str(tmp_path / "test.db")
        loader = SQLiteLoader(db_path=db_path)
        await loader.load(context_with_data)

        import aiosqlite

        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = [row[0] for row in await cursor.fetchall()]

        assert "knowledge_facts" in tables
        assert "pipeline_runs" in tables

    @pytest.mark.asyncio
    async def test_saves_facts(self, context_with_data, tmp_path):
        from backend.knowledge.pipeline.loaders.sqlite_loader import SQLiteLoader

        db_path = str(tmp_path / "test.db")
        loader = SQLiteLoader(db_path=db_path)
        await loader.load(context_with_data)

        import aiosqlite

        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM knowledge_facts")
            count = (await cursor.fetchone())[0]

        # 1 entity + 1 relationship + 1 event = 3 facts
        assert count == 3

    @pytest.mark.asyncio
    async def test_saves_pipeline_run(self, context_with_data, tmp_path):
        from backend.knowledge.pipeline.loaders.sqlite_loader import SQLiteLoader

        db_path = str(tmp_path / "test.db")
        loader = SQLiteLoader(db_path=db_path, run_id="test-run-1")
        await loader.load(context_with_data)

        import aiosqlite

        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute("SELECT id, status FROM pipeline_runs")
            row = await cursor.fetchone()

        assert row[0] == "test-run-1"
        assert row[1] == "completed"

    @pytest.mark.asyncio
    async def test_empty_context(self, tmp_path):
        from backend.knowledge.pipeline.loaders.sqlite_loader import SQLiteLoader

        db_path = str(tmp_path / "test.db")
        ctx = PipelineContext()
        ctx.document_id = uuid4()
        loader = SQLiteLoader(db_path=db_path)
        await loader.load(ctx)

        import aiosqlite

        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM knowledge_facts")
            count = (await cursor.fetchone())[0]

        assert count == 0
