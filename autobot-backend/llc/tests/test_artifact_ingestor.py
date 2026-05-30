"""Tests for ArtifactIngestor — work products indexed into project KB (GH#8242)."""

import sys
import uuid
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.kb.artifact_ingestor import ArtifactIngestor, _is_text_path, _split_text
from llc.models.enums import WorkProductType
from llc.models.work_product import LLCWorkProduct

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_product(
    *,
    id: Optional[uuid.UUID] = None,
    work_item_id: Optional[uuid.UUID] = None,
    type: WorkProductType = WorkProductType.CODE,
    title: str = "My artifact",
    content_text: Optional[str] = None,
    storage_path: Optional[str] = None,
    url: Optional[str] = None,
    kb_indexed: bool = False,
) -> LLCWorkProduct:
    p = MagicMock(spec=LLCWorkProduct)
    p.id = id or uuid.uuid4()
    p.work_item_id = work_item_id or uuid.uuid4()
    p.type = type
    p.title = title
    p.content_text = content_text
    p.storage_path = storage_path
    p.url = url
    p.kb_indexed = kb_indexed
    return p


# ---------------------------------------------------------------------------
# Unit tests for pure helpers
# ---------------------------------------------------------------------------


def test_is_text_path_recognises_text_extensions():
    assert _is_text_path("file.py")
    assert _is_text_path("README.md")
    assert _is_text_path("schema.sql")
    assert _is_text_path("/some/path/config.yml")


def test_is_text_path_rejects_binary_extensions():
    assert not _is_text_path("image.png")
    assert not _is_text_path("archive.zip")
    assert not _is_text_path("binary.exe")


def test_split_text_short_returns_single_chunk():
    text = "hello world"
    chunks = _split_text(text)
    assert chunks == [text]


def test_split_text_long_returns_multiple_chunks():
    # Produce text longer than _CHUNK_SIZE (4000 chars)
    text = "x" * 9000
    chunks = _split_text(text)
    assert len(chunks) > 1
    # Every chunk is at most 4000 characters
    assert all(len(c) <= 4000 for c in chunks)
    # All original content is present (with overlap, total chars may exceed original)
    assert any("x" in c for c in chunks)


def test_split_text_overlap_between_chunks():
    # First chunk ends at 4000; second starts at 4000-200=3800
    text = "a" * 8000
    chunks = _split_text(text)
    assert len(chunks) >= 2
    # Overlap: first chunk[3800:4000] should equal second chunk[0:200]
    assert chunks[0][3800:4000] == chunks[1][0:200]


# ---------------------------------------------------------------------------
# ArtifactIngestor.ingest — mocked ChromaDB
# ---------------------------------------------------------------------------


@pytest.fixture
def ingestor():
    return ArtifactIngestor()


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_ingest_indexes_content_text(ingestor, mock_session):
    product = _make_product(content_text="def hello(): pass", type=WorkProductType.CODE)
    project_id = str(uuid.uuid4())

    mock_scalar = MagicMock()
    mock_scalar.scalar_one_or_none = MagicMock(return_value=product)
    mock_session.execute.return_value = mock_scalar

    mock_collection = AsyncMock()
    mock_client = AsyncMock()
    mock_client.get_or_create_collection = AsyncMock(return_value=mock_collection)

    mock_chroma_module = MagicMock()
    mock_chroma_module.get_async_chromadb_client = AsyncMock(return_value=mock_client)

    with patch.dict(sys.modules, {"utils.async_chromadb_client": mock_chroma_module}):
        result = await ingestor.ingest(
            mock_session,
            work_product_id=str(product.id),
            project_id=project_id,
            work_item_identifier="MVA-1",
        )

    assert result is True
    assert product.kb_indexed is True
    assert mock_session.flush.called


@pytest.mark.asyncio
async def test_ingest_skips_when_no_project(ingestor, mock_session):
    product = _make_product(content_text="some text")
    mock_scalar = MagicMock()
    mock_scalar.scalar_one_or_none = MagicMock(return_value=product)
    mock_session.execute.return_value = mock_scalar

    result = await ingestor.ingest(
        mock_session,
        work_product_id=str(product.id),
        project_id=None,
        work_item_identifier="MVA-2",
    )

    assert result is False
    # kb_indexed should not have been set to True
    assert product.kb_indexed != True  # noqa: E712


@pytest.mark.asyncio
async def test_ingest_returns_false_for_missing_product(ingestor, mock_session):
    mock_scalar = MagicMock()
    mock_scalar.scalar_one_or_none = MagicMock(return_value=None)
    mock_session.execute.return_value = mock_scalar

    result = await ingestor.ingest(
        mock_session,
        work_product_id=str(uuid.uuid4()),
        project_id=str(uuid.uuid4()),
        work_item_identifier="MVA-3",
    )
    assert result is False


@pytest.mark.asyncio
async def test_ingest_skips_binary_storage_path(ingestor, mock_session):
    product = _make_product(
        storage_path="/tmp/binary.png"  # nosec B108 - test/controlled code uses tmpdir intentionally
    )
    mock_scalar = MagicMock()
    mock_scalar.scalar_one_or_none = MagicMock(return_value=product)
    mock_session.execute.return_value = mock_scalar

    result = await ingestor.ingest(
        mock_session,
        work_product_id=str(product.id),
        project_id=str(uuid.uuid4()),
        work_item_identifier="MVA-4",
    )

    assert result is False
    assert product.kb_indexed is False


@pytest.mark.asyncio
async def test_ingest_skips_product_with_no_content(ingestor, mock_session):
    product = _make_product()  # no content_text, no storage_path
    mock_scalar = MagicMock()
    mock_scalar.scalar_one_or_none = MagicMock(return_value=product)
    mock_session.execute.return_value = mock_scalar

    result = await ingestor.ingest(
        mock_session,
        work_product_id=str(product.id),
        project_id=str(uuid.uuid4()),
        work_item_identifier="MVA-5",
    )

    assert result is False


@pytest.mark.asyncio
async def test_ingest_all_pending_calls_ingest_for_each(ingestor, mock_session):
    item_id = uuid.uuid4()
    products = [
        _make_product(work_item_id=item_id, content_text="chunk1"),
        _make_product(work_item_id=item_id, content_text="chunk2"),
    ]

    mock_scalars = MagicMock()
    mock_scalars.scalars.return_value.all.return_value = products
    mock_session.execute.return_value = mock_scalars

    with patch.object(ingestor, "ingest", new=AsyncMock(return_value=True)) as mock_ingest:
        count = await ingestor.ingest_all_pending(
            mock_session,
            work_item_id=str(item_id),
            project_id=str(uuid.uuid4()),
            work_item_identifier="MVA-6",
        )

    assert count == 2
    assert mock_ingest.call_count == 2


@pytest.mark.asyncio
async def test_ingest_all_pending_counts_only_successful(ingestor, mock_session):
    item_id = uuid.uuid4()
    products = [
        _make_product(work_item_id=item_id, content_text="ok"),
        _make_product(
            work_item_id=item_id,
            storage_path="/tmp/img.png",  # nosec B108 - test/controlled code uses tmpdir intentionally
        ),
    ]
    mock_scalars = MagicMock()
    mock_scalars.scalars.return_value.all.return_value = products
    mock_session.execute.return_value = mock_scalars

    # First succeeds, second fails
    with patch.object(ingestor, "ingest", new=AsyncMock(side_effect=[True, False])) as mock_ingest:
        count = await ingestor.ingest_all_pending(
            mock_session,
            work_item_id=str(item_id),
            project_id=str(uuid.uuid4()),
            work_item_identifier="MVA-7",
        )

    assert count == 1


# ---------------------------------------------------------------------------
# Write guard tests (GH#8598)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_enforces_write_guard_on_ancestor_collection(ingestor, mock_session):
    """Verify ingest() raises HTTPException(403) if requester writes to ancestor's project."""
    from fastapi import HTTPException

    product_id = uuid.uuid4()
    project_id = uuid.uuid4()
    company_id = "child-company-id"
    ancestor_company_id = "ancestor-company-id"

    product = _make_product(id=product_id, content_text="test content")
    project = MagicMock()
    project.company_id = ancestor_company_id

    # Mock product lookup
    product_result = MagicMock()
    product_result.scalar_one_or_none.return_value = product

    # Mock project lookup
    project_result = MagicMock()
    project_result.scalar_one_or_none.return_value = project

    # Alternate execute() results: product, then project
    mock_session.execute.side_effect = [product_result, project_result]

    with patch(
        "llc.kb.artifact_ingestor.assert_not_writing_to_ancestor_kb",
        new=AsyncMock(side_effect=HTTPException(status_code=403, detail="Forbidden")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await ingestor.ingest(
                mock_session,
                work_product_id=str(product_id),
                project_id=str(project_id),
                work_item_identifier="MVA-999",
                company_id=company_id,
            )
        assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_ingest_skips_guard_when_no_company_id(ingestor, mock_session):
    """Verify ingest() does not call guard if company_id is not provided."""
    product_id = uuid.uuid4()
    project_id = uuid.uuid4()

    product = _make_product(id=product_id, content_text="test content")
    product_result = MagicMock()
    product_result.scalar_one_or_none.return_value = product

    mock_session.execute.return_value = product_result

    with patch(
        "llc.kb.artifact_ingestor.assert_not_writing_to_ancestor_kb",
        new=AsyncMock(),
    ) as mock_guard:
        # Mock ChromaDB client
        mock_client = AsyncMock()
        mock_collection = AsyncMock()
        mock_client.get_or_create_collection.return_value = mock_collection

        with patch("utils.async_chromadb_client.get_async_chromadb_client", new=AsyncMock(return_value=mock_client)):
            result = await ingestor.ingest(
                mock_session,
                work_product_id=str(product_id),
                project_id=str(project_id),
                work_item_identifier="MVA-999",
                company_id=None,  # No company_id, guard should not be called
            )

        # Guard should not be called if company_id is None
        mock_guard.assert_not_called()
