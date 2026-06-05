# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for AI Document CRUD + refinement API (Issue #3245)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.document import AIDocument
from tests.fixtures import make_async_redis, make_redis_pipeline

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FAKE_USER = {"user_id": "user-abc", "email": "test@example.com"}
_OTHER_USER = {"user_id": "user-xyz", "email": "other@example.com"}


def _make_doc(**kwargs) -> AIDocument:
    defaults = dict(title="Test Doc", content="Hello world", user_id="user-abc")
    defaults.update(kwargs)
    return AIDocument(**defaults)


@pytest.fixture()
def mock_redis():
    """Async Redis mock with pipeline support (#7280)."""
    pipe = make_redis_pipeline(execute_returns=[True, True])
    return make_async_redis(pipeline=pipe)


# ---------------------------------------------------------------------------
# AIDocument model tests
# ---------------------------------------------------------------------------


class TestAIDocumentModel:
    def test_defaults_populated(self):
        doc = _make_doc()
        assert doc.id
        assert doc.created_at
        assert doc.updated_at

    def test_redis_key_format(self):
        doc = _make_doc()
        assert doc.redis_key() == f"autobot:ai_document:{doc.id}"

    def test_touch_updates_timestamp(self):
        doc = _make_doc()
        old_ts = doc.updated_at
        import time

        time.sleep(0.001)
        doc.touch()
        assert doc.updated_at > old_ts

    def test_source_facts_default_empty(self):
        doc = _make_doc()
        assert doc.source_facts == []


# ---------------------------------------------------------------------------
# Endpoint unit tests — patch Redis, test business logic
# ---------------------------------------------------------------------------


class TestCreateDocument:
    @pytest.mark.asyncio
    async def test_creates_document(self, mock_redis):
        from api.documents import CreateDocumentRequest, create_document

        body = CreateDocumentRequest(title="New Doc", content="Some AI text")
        with patch("api.documents.get_async_redis_client", AsyncMock(return_value=mock_redis)):
            result = await create_document(body, current_user=_FAKE_USER)

        assert result["title"] == "New Doc"
        assert result["user_id"] == "user-abc"
        assert result["id"]

    @pytest.mark.asyncio
    async def test_creates_with_source_facts(self, mock_redis):
        from api.documents import CreateDocumentRequest, create_document

        body = CreateDocumentRequest(title="Grounded", source_facts=["fact-1", "fact-2"])
        with patch("api.documents.get_async_redis_client", AsyncMock(return_value=mock_redis)):
            result = await create_document(body, current_user=_FAKE_USER)

        assert result["source_facts"] == ["fact-1", "fact-2"]


class TestGetDocument:
    @pytest.mark.asyncio
    async def test_returns_document(self, mock_redis):
        from api.documents import get_document

        doc = _make_doc()
        mock_redis.get = AsyncMock(return_value=doc.model_dump_json())
        with patch("api.documents.get_async_redis_client", AsyncMock(return_value=mock_redis)):
            result = await get_document(doc.id, current_user=_FAKE_USER)

        assert result["id"] == doc.id

    @pytest.mark.asyncio
    async def test_raises_404_when_missing(self, mock_redis):
        from fastapi import HTTPException

        from api.documents import get_document

        mock_redis.get = AsyncMock(return_value=None)
        with patch("api.documents.get_async_redis_client", AsyncMock(return_value=mock_redis)):
            with pytest.raises(HTTPException) as exc_info:
                await get_document("nonexistent", current_user=_FAKE_USER)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_raises_403_for_wrong_owner(self, mock_redis):
        from fastapi import HTTPException

        from api.documents import get_document

        doc = _make_doc(user_id="user-abc")
        mock_redis.get = AsyncMock(return_value=doc.model_dump_json())
        with patch("api.documents.get_async_redis_client", AsyncMock(return_value=mock_redis)):
            with pytest.raises(HTTPException) as exc_info:
                await get_document(doc.id, current_user=_OTHER_USER)

        assert exc_info.value.status_code == 403


class TestUpdateDocument:
    @pytest.mark.asyncio
    async def test_updates_title_and_content(self, mock_redis):
        from api.documents import UpdateDocumentRequest, update_document

        doc = _make_doc()
        mock_redis.get = AsyncMock(return_value=doc.model_dump_json())
        body = UpdateDocumentRequest(title="Updated Title", content="New content")
        with patch("api.documents.get_async_redis_client", AsyncMock(return_value=mock_redis)):
            result = await update_document(doc.id, body, current_user=_FAKE_USER)

        assert result["title"] == "Updated Title"
        assert result["content"] == "New content"

    @pytest.mark.asyncio
    async def test_partial_update_leaves_other_fields(self, mock_redis):
        from api.documents import UpdateDocumentRequest, update_document

        doc = _make_doc(content="original content")
        mock_redis.get = AsyncMock(return_value=doc.model_dump_json())
        body = UpdateDocumentRequest(title="New Title Only")
        with patch("api.documents.get_async_redis_client", AsyncMock(return_value=mock_redis)):
            result = await update_document(doc.id, body, current_user=_FAKE_USER)

        assert result["content"] == "original content"
        assert result["title"] == "New Title Only"

    @pytest.mark.asyncio
    async def test_can_set_nullable_fields_to_null(self, mock_redis):
        """Test fix for #9525: nullable fields can be explicitly set to null."""
        from api.documents import UpdateDocumentRequest, update_document

        doc = _make_doc(
            title="Original Title",
            content="Original content",
            tags=["tag1", "tag2"],
            metadata={"key": "value"},
        )
        mock_redis.get = AsyncMock(return_value=doc.model_dump_json())

        # Set all nullable fields to null
        body = UpdateDocumentRequest(title=None, content=None, tags=None, metadata=None)
        with patch("api.documents.get_async_redis_client", AsyncMock(return_value=mock_redis)):
            result = await update_document(doc.id, body, current_user=_FAKE_USER)

        # All fields should be null (not unchanged)
        assert result["title"] is None
        assert result["content"] is None
        assert result["tags"] is None
        assert result["metadata"] is None

    @pytest.mark.asyncio
    async def test_validation_still_enforced_when_not_null(self, mock_redis):
        """Test fix for #9525: validation (e.g., title min_length) still works."""
        from fastapi import HTTPException

        from api.documents import UpdateDocumentRequest, update_document

        doc = _make_doc()
        mock_redis.get = AsyncMock(return_value=doc.model_dump_json())

        # Empty string should fail validation (min_length=1)
        with pytest.raises(Exception):  # Pydantic ValidationError
            UpdateDocumentRequest(title="")

        # But null should be allowed
        body = UpdateDocumentRequest(title=None)
        with patch("api.documents.get_async_redis_client", AsyncMock(return_value=mock_redis)):
            result = await update_document(doc.id, body, current_user=_FAKE_USER)
        assert result["title"] is None


class TestDeleteDocument:
    @pytest.mark.asyncio
    async def test_deletes_document(self, mock_redis):
        from api.documents import delete_document

        doc = _make_doc()
        mock_redis.get = AsyncMock(return_value=doc.model_dump_json())
        with patch("api.documents.get_async_redis_client", AsyncMock(return_value=mock_redis)):
            result = await delete_document(doc.id, current_user=_FAKE_USER)

        # delete_document returns None (204)
        assert result is None
        mock_redis.pipeline().delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_404_when_missing(self, mock_redis):
        from fastapi import HTTPException

        from api.documents import delete_document

        mock_redis.get = AsyncMock(return_value=None)
        with patch("api.documents.get_async_redis_client", AsyncMock(return_value=mock_redis)):
            with pytest.raises(HTTPException) as exc_info:
                await delete_document("ghost-id", current_user=_FAKE_USER)

        assert exc_info.value.status_code == 404


class TestListDocuments:
    @pytest.mark.asyncio
    async def test_empty_index_returns_empty_list(self, mock_redis):
        from api.documents import list_documents

        mock_redis.smembers = AsyncMock(return_value=set())
        with patch("api.documents.get_async_redis_client", AsyncMock(return_value=mock_redis)):
            result = await list_documents(limit=50, offset=0, current_user=_FAKE_USER)

        assert result == {"documents": [], "total": 0}

    @pytest.mark.asyncio
    async def test_lists_user_documents(self, mock_redis):
        from api.documents import list_documents

        doc1 = _make_doc(title="Doc A")
        doc2 = _make_doc(title="Doc B")
        mock_redis.smembers = AsyncMock(return_value={doc1.id, doc2.id})
        pipe = AsyncMock()
        pipe.get = MagicMock()
        pipe.execute = AsyncMock(return_value=[doc1.model_dump_json(), doc2.model_dump_json()])
        mock_redis.pipeline = MagicMock(return_value=pipe)
        with patch("api.documents.get_async_redis_client", AsyncMock(return_value=mock_redis)):
            result = await list_documents(limit=50, offset=0, current_user=_FAKE_USER)

        assert result["total"] == 2
        assert len(result["documents"]) == 2
