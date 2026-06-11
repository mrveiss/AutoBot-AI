# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for transcript AI analysis and KB integration (MVA-2176, #9863).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.schemas_transcripts import (
    AnalysisType,
    TranscriptKBPushRequest,
)

MOCK_USER = {"user_id": "test-user", "roles": ["user"]}


def _make_raw_request(db) -> SimpleNamespace:
    """Build a request-like object exposing app.state.transcriber_db."""
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(transcriber_db=db))
    )


def _make_db(recording: dict | None) -> AsyncMock:
    db = AsyncMock()
    db.get_recording = AsyncMock(return_value=recording)
    return db


DEFAULT_RECORDING = {"id": 456, "user_id": "default", "status": "complete"}


@pytest.mark.asyncio
async def test_kb_push_success():
    """Test successful KB push creates entry with correct metadata."""
    from api.transcripts import push_transcript_to_kb

    # Mock KB
    mock_kb = AsyncMock()
    mock_kb.add_document = AsyncMock(
        return_value={"status": "success", "doc_id": "test-doc-123"}
    )

    # Mock request
    request = TranscriptKBPushRequest(
        segment_text="This is a test transcript segment.",
        segment_start=10.5,
        segment_end=25.3,
        speaker="John",
        confidence=0.95,
    )

    with patch("api.transcripts.get_knowledge_base", return_value=mock_kb):
        response = await push_transcript_to_kb(
            transcript_id="456",
            request=request,
            raw_request=_make_raw_request(_make_db(DEFAULT_RECORDING)),
            user=MOCK_USER,
        )

    # Verify response
    assert response.success is True
    assert response.doc_id == "test-doc-123"
    assert "added to Knowledge Base" in response.message

    # Verify KB was called with correct parameters
    mock_kb.add_document.assert_called_once()
    call_args = mock_kb.add_document.call_args
    assert call_args.kwargs["content"] == "This is a test transcript segment."

    # Verify metadata
    metadata = call_args.kwargs["metadata"]
    assert metadata["source_type"] == "transcript"
    assert metadata["transcript_id"] == "456"
    assert metadata["source"] == "transcript:456"
    assert metadata["segment_start"] == 10.5
    assert metadata["segment_end"] == 25.3
    assert metadata["speaker"] == "John"
    assert metadata["confidence"] == 0.95
    assert metadata["verification_status"] == "unverified"
    assert metadata["user_id"] == "test-user"


@pytest.mark.asyncio
async def test_kb_push_without_timing():
    """Test KB push without segment timing still works."""
    from api.transcripts import push_transcript_to_kb

    mock_kb = AsyncMock()
    mock_kb.add_document = AsyncMock(
        return_value={"status": "success", "doc_id": "test-doc-789"}
    )

    request = TranscriptKBPushRequest(
        segment_text="Segment without timing.",
    )

    with patch("api.transcripts.get_knowledge_base", return_value=mock_kb):
        response = await push_transcript_to_kb(
            transcript_id="456",
            request=request,
            raw_request=_make_raw_request(_make_db(DEFAULT_RECORDING)),
            user=MOCK_USER,
        )

    assert response.success is True
    assert response.doc_id == "test-doc-789"

    # Verify timing fields are not in metadata
    call_args = mock_kb.add_document.call_args
    metadata = call_args.kwargs["metadata"]
    assert "segment_start" not in metadata
    assert "segment_end" not in metadata


@pytest.mark.asyncio
async def test_kb_push_failure():
    """Test KB push handles KB failure gracefully."""
    from api.transcripts import push_transcript_to_kb

    mock_kb = AsyncMock()
    mock_kb.add_document = AsyncMock(
        return_value={"status": "error", "message": "KB timeout"}
    )

    request = TranscriptKBPushRequest(
        segment_text="Test segment.",
    )

    with patch("api.transcripts.get_knowledge_base", return_value=mock_kb):
        response = await push_transcript_to_kb(
            transcript_id="456",
            request=request,
            raw_request=_make_raw_request(_make_db(DEFAULT_RECORDING)),
            user=MOCK_USER,
        )

    assert response.success is False
    # KB error status surfaces the KB-provided message
    assert response.message == "KB timeout"


@pytest.mark.asyncio
async def test_kb_push_exception():
    """Test KB push handles exceptions gracefully."""
    from api.transcripts import push_transcript_to_kb

    mock_kb = AsyncMock()
    mock_kb.add_document = AsyncMock(side_effect=Exception("Database error"))

    request = TranscriptKBPushRequest(
        segment_text="Test segment.",
    )

    with patch("api.transcripts.get_knowledge_base", return_value=mock_kb):
        response = await push_transcript_to_kb(
            transcript_id="456",
            request=request,
            raw_request=_make_raw_request(_make_db(DEFAULT_RECORDING)),
            user=MOCK_USER,
        )

    assert response.success is False
    # Security: Error message should be generic
    assert "failed" in response.message.lower()
    # Security: Should NOT expose internal exception details
    assert "Database error" not in response.message


@pytest.mark.asyncio
async def test_kb_push_unknown_recording_404():
    """Test KB push rejects transcript ids with no backing recording."""
    from api.transcripts import push_transcript_to_kb

    request = TranscriptKBPushRequest(segment_text="Test segment.")

    with pytest.raises(HTTPException) as exc_info:
        await push_transcript_to_kb(
            transcript_id="999",
            request=request,
            raw_request=_make_raw_request(_make_db(None)),
            user=MOCK_USER,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_kb_push_non_numeric_id_404():
    """Test KB push rejects non-numeric transcript ids."""
    from api.transcripts import push_transcript_to_kb

    request = TranscriptKBPushRequest(segment_text="Test segment.")

    with pytest.raises(HTTPException) as exc_info:
        await push_transcript_to_kb(
            transcript_id="not-a-recording",
            request=request,
            raw_request=_make_raw_request(_make_db(DEFAULT_RECORDING)),
            user=MOCK_USER,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_kb_push_other_users_recording_404():
    """Test KB push hides recordings owned by another user."""
    from api.transcripts import push_transcript_to_kb

    request = TranscriptKBPushRequest(segment_text="Test segment.")
    foreign = {"id": 456, "user_id": "someone-else", "status": "complete"}

    with pytest.raises(HTTPException) as exc_info:
        await push_transcript_to_kb(
            transcript_id="456",
            request=request,
            raw_request=_make_raw_request(_make_db(foreign)),
            user=MOCK_USER,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_kb_push_storage_unavailable_503():
    """Test KB push returns 503 when transcriber storage is not initialized."""
    from api.transcripts import push_transcript_to_kb

    request = TranscriptKBPushRequest(segment_text="Test segment.")
    raw_request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))

    with pytest.raises(HTTPException) as exc_info:
        await push_transcript_to_kb(
            transcript_id="456",
            request=request,
            raw_request=raw_request,
            user=MOCK_USER,
        )

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_load_transcript_content_uses_segments():
    """Test transcript content is built from stored segments."""
    from api.transcripts import _load_transcript_content

    db = _make_db(DEFAULT_RECORDING)
    state = SimpleNamespace(transcriber_db=db)
    segments = [
        {"text": "Hello world", "speaker_name": "John", "start": 0.0, "notes": []}
    ]

    with patch("api.transcripts._build_segment_list", AsyncMock(return_value=segments)):
        content = await _load_transcript_content(state, "456", "test-user")

    assert "Hello world" in content


@pytest.mark.asyncio
async def test_load_transcript_content_incomplete_400():
    """Test analysis of an untranscribed recording is rejected."""
    from api.transcripts import _load_transcript_content

    pending = {"id": 456, "user_id": "default", "status": "processing"}
    state = SimpleNamespace(transcriber_db=_make_db(pending))

    with pytest.raises(HTTPException) as exc_info:
        await _load_transcript_content(state, "456", "test-user")

    assert exc_info.value.status_code == 400


def test_analysis_prompt_generation():
    """Test analysis prompt generation for different types."""
    from api.transcripts import _get_analysis_prompt

    content = "Sample transcript content"

    # Test SUMMARIZE
    prompt = _get_analysis_prompt(AnalysisType.SUMMARIZE, content)
    assert "Summarize" in prompt
    assert content in prompt

    # Test KEY_FACTS
    prompt = _get_analysis_prompt(AnalysisType.KEY_FACTS, content)
    assert "key facts" in prompt.lower()
    assert content in prompt

    # Test PROTOCOL
    prompt = _get_analysis_prompt(AnalysisType.PROTOCOL, content)
    assert "protocol" in prompt.lower()
    assert content in prompt

    # Test CUSTOM with custom_prompt
    custom = "Extract action items"
    prompt = _get_analysis_prompt(AnalysisType.CUSTOM, content, custom)
    assert custom in prompt
    assert content in prompt


def test_analysis_prompt_custom_requires_prompt():
    """Test CUSTOM analysis type requires custom_prompt."""
    from api.transcripts import _get_analysis_prompt

    with pytest.raises(ValueError, match="custom_prompt"):
        _get_analysis_prompt(AnalysisType.CUSTOM, "content", None)
