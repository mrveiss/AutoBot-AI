# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for transcript AI analysis and KB integration (MVA-2176).
"""

from unittest.mock import AsyncMock, patch

import pytest

from api.schemas_transcripts import (
    AnalysisType,
    TranscriptKBPushRequest,
)


@pytest.mark.asyncio
async def test_kb_push_success():
    """Test successful KB push creates entry with correct metadata."""
    from api.transcripts import push_transcript_to_kb

    # Mock KB
    mock_kb = AsyncMock()
    mock_kb.add_document = AsyncMock(return_value={"status": "success", "doc_id": "test-doc-123"})

    # Mock request
    request = TranscriptKBPushRequest(
        segment_text="This is a test transcript segment.",
        segment_start=10.5,
        segment_end=25.3,
        speaker="John",
        confidence=0.95,
    )

    # Mock user
    mock_user = {"user_id": "test-user", "roles": ["user"]}

    with patch("api.transcripts.get_knowledge_base", return_value=mock_kb):
        response = await push_transcript_to_kb(
            transcript_id="transcript-456",
            request=request,
            user=mock_user,
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
    assert metadata["transcript_id"] == "transcript-456"
    assert metadata["source"] == "transcript:transcript-456"
    assert metadata["segment_start"] == 10.5
    assert metadata["segment_end"] == 25.3
    assert metadata["speaker"] == "John"
    assert metadata["confidence"] == 0.95
    assert metadata["verification_status"] == "unverified"


@pytest.mark.asyncio
async def test_kb_push_without_timing():
    """Test KB push without segment timing still works."""
    from api.transcripts import push_transcript_to_kb

    mock_kb = AsyncMock()
    mock_kb.add_document = AsyncMock(return_value={"status": "success", "doc_id": "test-doc-789"})

    request = TranscriptKBPushRequest(
        segment_text="Segment without timing.",
    )

    mock_user = {"user_id": "test-user", "roles": ["user"]}

    with patch("api.transcripts.get_knowledge_base", return_value=mock_kb):
        response = await push_transcript_to_kb(
            transcript_id="transcript-789",
            request=request,
            user=mock_user,
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
    mock_kb.add_document = AsyncMock(return_value={"status": "error", "message": "KB timeout"})

    request = TranscriptKBPushRequest(
        segment_text="Test segment.",
    )

    mock_user = {"user_id": "test-user", "roles": ["user"]}

    with patch("api.transcripts.get_knowledge_base", return_value=mock_kb):
        response = await push_transcript_to_kb(
            transcript_id="transcript-fail",
            request=request,
            user=mock_user,
        )

    assert response.success is False
    # Security: Error message should be generic, not expose internal details
    assert "failed" in response.message.lower()


@pytest.mark.asyncio
async def test_kb_push_exception():
    """Test KB push handles exceptions gracefully."""
    from api.transcripts import push_transcript_to_kb

    mock_kb = AsyncMock()
    mock_kb.add_document = AsyncMock(side_effect=Exception("Database error"))

    request = TranscriptKBPushRequest(
        segment_text="Test segment.",
    )

    mock_user = {"user_id": "test-user", "roles": ["user"]}

    with patch("api.transcripts.get_knowledge_base", return_value=mock_kb):
        response = await push_transcript_to_kb(
            transcript_id="transcript-error",
            request=request,
            user=mock_user,
        )

    assert response.success is False
    # Security: Error message should be generic
    assert "failed" in response.message.lower()
    # Security: Should NOT expose internal exception details
    assert "Database error" not in response.message


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
