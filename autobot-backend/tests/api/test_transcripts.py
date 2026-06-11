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
    # Security: KB-internal reason is logged, client gets a generic message
    assert response.message == "Failed to add to Knowledge Base"
    assert "KB timeout" not in response.message


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

    with patch("api.transcripts.build_segment_list", AsyncMock(return_value=segments)):
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


def test_validate_analysis_request_custom_requires_prompt():
    """Test CUSTOM analysis type requires custom_prompt."""
    from api.schemas_transcripts import TranscriptAnalyzeRequest
    from api.transcripts import _validate_analysis_request

    # Non-custom types pass without a prompt
    _validate_analysis_request(
        TranscriptAnalyzeRequest(analysis_type=AnalysisType.SUMMARIZE)
    )
    # Custom with a prompt passes
    _validate_analysis_request(
        TranscriptAnalyzeRequest(
            analysis_type=AnalysisType.CUSTOM, custom_prompt="Extract action items"
        )
    )


def test_validate_analysis_request_custom_missing_prompt_raises():
    """Test CUSTOM analysis without custom_prompt raises ValueError."""
    from api.schemas_transcripts import TranscriptAnalyzeRequest
    from api.transcripts import _validate_analysis_request

    with pytest.raises(ValueError, match="custom_prompt"):
        _validate_analysis_request(
            TranscriptAnalyzeRequest(analysis_type=AnalysisType.CUSTOM)
        )


# --- WebSocket endpoint tests (#9863 review) ---


def _make_ws_client(db, user):
    """Build a TestClient over a minimal app mounting the transcripts router."""
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    from api.transcripts import router

    app = FastAPI()
    app.include_router(router, prefix="/api")
    if db is not None:
        app.state.transcriber_db = db
    return TestClient(app)


def test_ws_analyze_rejects_unauthenticated():
    """Test WS closes 4001 before accept when authentication fails."""
    from starlette.websockets import WebSocketDisconnect

    client = _make_ws_client(_make_db(DEFAULT_RECORDING), user=None)

    with patch("api.transcripts.authenticate_websocket", AsyncMock(return_value=None)):
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/api/transcripts/456/analyze"):
                pass

    assert exc_info.value.code == 4001


def test_ws_analyze_streams_and_closes():
    """Test WS streams analysis chunks for a valid recording, then closes."""
    from starlette.websockets import WebSocketDisconnect

    async def fake_stream(content, request):
        yield "analysis-chunk"

    client = _make_ws_client(_make_db(DEFAULT_RECORDING), user=MOCK_USER)
    segments = [{"text": "Hello", "speaker_name": "John", "start": 0.0, "notes": []}]

    with (
        patch(
            "api.transcripts.authenticate_websocket",
            AsyncMock(return_value=MOCK_USER),
        ),
        patch("api.transcripts.build_segment_list", AsyncMock(return_value=segments)),
        patch("api.transcripts._stream_analysis", fake_stream),
    ):
        with client.websocket_connect("/api/transcripts/456/analyze") as ws:
            ws.send_json({"analysis_type": "summarize"})
            assert ws.receive_text() == "analysis-chunk"
            with pytest.raises(WebSocketDisconnect) as exc_info:
                ws.receive_text()

    assert exc_info.value.code == 1000


def test_ws_analyze_unknown_recording_closes_4004():
    """Test WS sends an error payload and closes 4004 for unknown recordings."""
    from starlette.websockets import WebSocketDisconnect

    client = _make_ws_client(_make_db(None), user=MOCK_USER)

    with patch(
        "api.transcripts.authenticate_websocket", AsyncMock(return_value=MOCK_USER)
    ):
        with client.websocket_connect("/api/transcripts/999/analyze") as ws:
            ws.send_json({"analysis_type": "summarize"})
            assert ws.receive_json() == {"error": "Transcript not found"}
            with pytest.raises(WebSocketDisconnect) as exc_info:
                ws.receive_text()

    assert exc_info.value.code == 4004
