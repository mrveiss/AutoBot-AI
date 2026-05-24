"""Tests for AgentCapabilityIndexer — agent capabilities indexed into company KB (GH#8244)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.kb.capability_indexer import AgentCapabilityIndexer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def indexer():
    return AgentCapabilityIndexer()


@pytest.fixture
def company_id():
    return str(uuid.uuid4())


@pytest.fixture
def agent_id():
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Unit tests for collection naming
# ---------------------------------------------------------------------------


def test_collection_name_format(indexer, company_id):
    """Collection name should be company:{company_id}:agents."""
    expected = f"company:{company_id}:agents"
    assert indexer._collection_name(company_id) == expected


def test_doc_id_format(indexer, agent_id):
    """Document ID should be agent:{agent_id}."""
    expected = f"agent:{agent_id}"
    assert indexer._doc_id(agent_id) == expected


# ---------------------------------------------------------------------------
# Async tests for indexing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_index_creates_capability_document(indexer, company_id, agent_id):
    """Index should create a capability document in the company agents collection."""
    mock_collection = AsyncMock()
    mock_kb = MagicMock()
    mock_kb._async_chroma_client.get_or_create_collection = AsyncMock(
        return_value=mock_collection
    )

    with patch("llc.kb.capability_indexer.get_knowledge_base", return_value=mock_kb):
        doc_id = await indexer.index(
            agent_id=agent_id,
            company_id=company_id,
            agent_name="Alice",
            title="Security Engineer",
            role="security",
            capabilities="Security audits, penetration testing, vulnerability assessment",
            manager_name="Bob",
        )

    assert doc_id == f"agent:{agent_id}"
    mock_kb._async_chroma_client.get_or_create_collection.assert_called_once_with(
        name=f"company:{company_id}:agents",
        metadata={"entity_type": "company", "entity_id": company_id},
    )
    mock_collection.upsert.assert_called_once()
    call_args = mock_collection.upsert.call_args
    assert call_args[1]["ids"] == [f"agent:{agent_id}"]
    assert "Alice" in call_args[1]["documents"][0]
    assert "Security audits" in call_args[1]["documents"][0]
    assert "Reports to: Bob" in call_args[1]["documents"][0]


@pytest.mark.asyncio
async def test_index_without_manager_name(indexer, company_id, agent_id):
    """Index should work without manager_name."""
    mock_collection = AsyncMock()
    mock_kb = MagicMock()
    mock_kb._async_chroma_client.get_or_create_collection = AsyncMock(
        return_value=mock_collection
    )

    with patch("llc.kb.capability_indexer.get_knowledge_base", return_value=mock_kb):
        await indexer.index(
            agent_id=agent_id,
            company_id=company_id,
            agent_name="Charlie",
            title="Developer",
            role="engineering",
            capabilities="Backend development, API design",
        )

    call_args = mock_collection.upsert.call_args
    doc_text = call_args[1]["documents"][0]
    assert "Charlie" in doc_text
    assert "Backend development" in doc_text
    assert "Reports to:" not in doc_text


@pytest.mark.asyncio
async def test_index_handles_kb_failure(indexer, company_id, agent_id):
    """Index should handle KB failures gracefully and log."""
    mock_kb = MagicMock()
    mock_kb._async_chroma_client.get_or_create_collection = AsyncMock(
        side_effect=RuntimeError("KB connection failed")
    )

    with patch("llc.kb.capability_indexer.get_knowledge_base", return_value=mock_kb):
        with patch("llc.kb.capability_indexer.logger") as mock_logger:
            await indexer.index(
                agent_id=agent_id,
                company_id=company_id,
                agent_name="Dave",
                title="Manager",
                role="management",
                capabilities="Team leadership",
            )

            mock_logger.exception.assert_called_once()
            assert "Failed to upsert agent capability" in str(
                mock_logger.exception.call_args
            )


# ---------------------------------------------------------------------------
# Async tests for removal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_deletes_capability_document(indexer, company_id, agent_id):
    """Remove should delete the agent capability document from the collection."""
    mock_collection = AsyncMock()
    mock_kb = MagicMock()
    mock_kb._async_chroma_client.get_collection = AsyncMock(
        return_value=mock_collection
    )

    with patch("llc.kb.capability_indexer.get_knowledge_base", return_value=mock_kb):
        await indexer.remove(agent_id=agent_id, company_id=company_id)

    mock_kb._async_chroma_client.get_collection.assert_called_once_with(
        f"company:{company_id}:agents"
    )
    mock_collection.delete.assert_called_once_with(ids=[f"agent:{agent_id}"])


@pytest.mark.asyncio
async def test_remove_handles_missing_collection(indexer, company_id, agent_id):
    """Remove should handle missing collection gracefully."""
    mock_kb = MagicMock()
    mock_kb._async_chroma_client.get_collection = AsyncMock(
        side_effect=Exception("Collection not found")
    )

    with patch("llc.kb.capability_indexer.get_knowledge_base", return_value=mock_kb):
        with patch("llc.kb.capability_indexer.logger") as mock_logger:
            await indexer.remove(agent_id=agent_id, company_id=company_id)

            mock_logger.debug.assert_called_once()
            assert "not found" in str(mock_logger.debug.call_args).lower()


@pytest.mark.asyncio
async def test_remove_handles_delete_failure(indexer, company_id, agent_id):
    """Remove should handle delete failures gracefully and log."""
    mock_collection = AsyncMock()
    mock_collection.delete = AsyncMock(side_effect=RuntimeError("Delete failed"))
    mock_kb = MagicMock()
    mock_kb._async_chroma_client.get_collection = AsyncMock(
        return_value=mock_collection
    )

    with patch("llc.kb.capability_indexer.get_knowledge_base", return_value=mock_kb):
        with patch("llc.kb.capability_indexer.logger") as mock_logger:
            await indexer.remove(agent_id=agent_id, company_id=company_id)

            mock_logger.exception.assert_called_once()
            assert "Failed to delete agent capability" in str(
                mock_logger.exception.call_args
            )


# ---------------------------------------------------------------------------
# Integration-style tests (with mocked KB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_index_and_remove_lifecycle(indexer, company_id, agent_id):
    """Full lifecycle: index an agent, then remove it."""
    mock_collection = AsyncMock()
    mock_kb = MagicMock()
    mock_kb._async_chroma_client.get_or_create_collection = AsyncMock(
        return_value=mock_collection
    )
    mock_kb._async_chroma_client.get_collection = AsyncMock(
        return_value=mock_collection
    )

    with patch("llc.kb.capability_indexer.get_knowledge_base", return_value=mock_kb):
        # Index the agent
        doc_id = await indexer.index(
            agent_id=agent_id,
            company_id=company_id,
            agent_name="Eve",
            title="QA Engineer",
            role="qa",
            capabilities="Test automation, performance testing",
        )

        assert doc_id == f"agent:{agent_id}"
        assert mock_collection.upsert.call_count == 1

        # Remove the agent
        await indexer.remove(agent_id=agent_id, company_id=company_id)

        assert mock_collection.delete.call_count == 1
        mock_collection.delete.assert_called_with(ids=[f"agent:{agent_id}"])
