# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/transcriber/tests/test_kb_push.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
from unittest.mock import AsyncMock, patch

import pytest

from transcriber.knowledge.kb_push import push_to_kb


@pytest.mark.asyncio
async def test_push_to_kb_formats_documents():
    segments = [
        {"start": 0.0, "end": 1.5, "speaker_name": "Alice", "text": "Hello world", "notes": []},
        {"start": 1.5, "end": 3.0, "speaker_name": "Bob", "text": "Goodbye", "notes": []},
    ]
    mock_indexer = AsyncMock()
    mock_indexer.add_documents = AsyncMock(return_value={"indexed": 2})
    with patch("transcriber.knowledge.kb_push._get_indexer", return_value=mock_indexer):
        result = await push_to_kb(
            recording_id=1,
            recording_filename="meeting.wav",
            segments=segments,
            collection_id="my-kb",
            pushed_by="u1",
        )
    assert result["indexed"] == 2
    call_args = mock_indexer.add_documents.call_args
    docs = call_args.kwargs.get("documents") or call_args.args[0]
    assert len(docs) == 2
    assert "Alice" in docs[0]["content"]
    assert "00:00:00" in docs[0]["content"]


@pytest.mark.asyncio
async def test_push_to_kb_returns_count():
    segments = [{"start": 0.0, "end": 1.0, "speaker_name": "A", "text": "Hi", "notes": []}]
    mock_indexer = AsyncMock()
    mock_indexer.add_documents = AsyncMock(return_value={"indexed": 1})
    with patch("transcriber.knowledge.kb_push._get_indexer", return_value=mock_indexer):
        result = await push_to_kb(1, "test.wav", segments, "col", "u1")
    assert result["indexed"] == 1
