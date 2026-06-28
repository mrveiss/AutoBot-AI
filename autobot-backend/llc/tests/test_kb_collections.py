# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for KbCollectionManager (GH#8235)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.kb.collections import KbCollectionManager


@pytest.fixture
def manager():
    return KbCollectionManager()


@pytest.fixture
def entity_id():
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


class TestCollectionName:
    def test_basic(self, manager, entity_id):
        assert manager.collection_name("company", entity_id) == f"company:{entity_id}"

    def test_with_suffix(self, manager, entity_id):
        assert manager.collection_name("company", entity_id, "agents") == f"company:{entity_id}:agents"

    def test_string_id(self, manager):
        assert manager.collection_name("project", "abc-123") == "project:abc-123"

    def test_prefix_constants(self):
        assert KbCollectionManager.COMPANY_PREFIX == "company"
        assert KbCollectionManager.PROJECT_PREFIX == "project"
        assert KbCollectionManager.SPRINT_PREFIX == "sprint"
        assert KbCollectionManager.WORK_ITEM_PREFIX == "work_item"


class TestEnsureCollection:
    @pytest.mark.asyncio
    async def test_creates_collection(self, manager, entity_id):
        mock_collection = MagicMock()
        mock_chroma = AsyncMock()
        mock_chroma.get_or_create_collection = AsyncMock(return_value=mock_collection)
        mock_kb = MagicMock()
        mock_kb._async_chroma_client = mock_chroma

        with patch("knowledge.get_knowledge_base", AsyncMock(return_value=mock_kb)):
            name = await manager.ensure_collection("company", entity_id)

        assert name == f"company:{entity_id}"
        mock_chroma.get_or_create_collection.assert_called_once_with(
            name=f"company:{entity_id}",
            metadata={"entity_type": "company", "entity_id": str(entity_id)},
        )

    @pytest.mark.asyncio
    async def test_raises_on_chroma_error(self, manager, entity_id):
        mock_chroma = AsyncMock()
        mock_chroma.get_or_create_collection = AsyncMock(side_effect=Exception("boom"))
        mock_kb = MagicMock()
        mock_kb._async_chroma_client = mock_chroma

        with patch("knowledge.get_knowledge_base", AsyncMock(return_value=mock_kb)):
            with pytest.raises(RuntimeError, match="Failed to ensure KB collection"):
                await manager.ensure_collection("project", entity_id)


class TestArchiveCollection:
    @pytest.mark.asyncio
    async def test_copies_and_deletes(self, manager, entity_id):
        docs = {"ids": ["d1"], "embeddings": [[0.1]], "metadatas": [{}], "documents": ["text"]}
        original = AsyncMock()
        original.get = AsyncMock(return_value=docs)
        archived = AsyncMock()

        mock_chroma = AsyncMock()
        mock_chroma.get_collection = AsyncMock(return_value=original)
        mock_chroma.create_collection = AsyncMock(return_value=archived)
        mock_chroma.delete_collection = AsyncMock()

        mock_kb = MagicMock()
        mock_kb._async_chroma_client = mock_chroma

        with patch("knowledge.get_knowledge_base", AsyncMock(return_value=mock_kb)):
            archived_name = await manager.archive_collection("sprint", entity_id)

        assert archived_name.startswith(f"sprint:{entity_id}:archived:")
        mock_chroma.delete_collection.assert_called_once_with(f"sprint:{entity_id}")
        archived.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_collection_is_noop(self, manager, entity_id):
        mock_chroma = AsyncMock()
        mock_chroma.get_collection = AsyncMock(side_effect=Exception("not found"))
        mock_chroma.create_collection = AsyncMock()
        mock_chroma.delete_collection = AsyncMock()

        mock_kb = MagicMock()
        mock_kb._async_chroma_client = mock_chroma

        with patch("knowledge.get_knowledge_base", AsyncMock(return_value=mock_kb)):
            archived_name = await manager.archive_collection("sprint", entity_id)

        assert archived_name.startswith(f"sprint:{entity_id}:archived:")
        mock_chroma.delete_collection.assert_not_called()


class TestMergeCollection:
    @pytest.mark.asyncio
    async def test_copies_documents(self, manager, entity_id):
        project_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
        docs = {"ids": ["d1"], "embeddings": None, "metadatas": [{}], "documents": ["text"]}

        src = AsyncMock()
        src.get = AsyncMock(return_value=docs)
        dst = AsyncMock()

        mock_chroma = AsyncMock()
        mock_chroma.get_collection = AsyncMock(return_value=src)
        mock_chroma.get_or_create_collection = AsyncMock(return_value=dst)

        mock_kb = MagicMock()
        mock_kb._async_chroma_client = mock_chroma

        with patch("knowledge.get_knowledge_base", AsyncMock(return_value=mock_kb)):
            await manager.merge_collection("sprint", entity_id, "project", project_id)

        dst.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_summarize_flag_short_circuits(self, manager, entity_id):
        project_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
        mock_kb = MagicMock()

        with patch("knowledge.get_knowledge_base", AsyncMock(return_value=mock_kb)):
            await manager.merge_collection("sprint", entity_id, "project", project_id, summarize=True)

        mock_kb._async_chroma_client.get_collection.assert_not_called()
