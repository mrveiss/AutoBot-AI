# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Unit tests for AudioConnector — Issue #3243.

Tests cover:
  - source_id stability
  - discover_sources: local file and URL paths
  - detect_changes: all sources returned as "added"
  - fetch_content: NPU path, CPU fallback path, YouTube metadata path
  - _validate_local_path: rejects relative paths, missing files, bad extensions
  - get_audio_pipeline_config: validates returned structure
"""

import os
import sys
import tempfile
from unittest.mock import AsyncMock, patch

import pytest

from autobot_shared.datetime_utils import datetime_now

# ---------------------------------------------------------------------------
# Ensure the autobot-backend package root is on sys.path
# ---------------------------------------------------------------------------
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from knowledge.connectors.audio_connector import (
    AudioConnector,
    _is_youtube_url,
    _source_id_for,
    _validate_local_path,
)
from knowledge.connectors.models import ConnectorConfig
from knowledge.pipeline.config import get_audio_pipeline_config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(sources=None, **extra):
    return ConnectorConfig(
        connector_id="test-audio-001",
        connector_type="audio",
        name="test_audio",
        config={
            "sources": sources or [],
            "whisper_model": "tiny",
            "language": "en",
            **extra,
        },
    )


# ---------------------------------------------------------------------------
# _source_id_for
# ---------------------------------------------------------------------------


def test_source_id_stable():
    sid1 = _source_id_for("https://youtu.be/abc123")
    sid2 = _source_id_for("https://youtu.be/abc123")
    assert sid1 == sid2
    assert len(sid1) == 32


def test_source_id_differs_for_different_sources():
    assert _source_id_for("/tmp/a.mp3") != _source_id_for(  # nosec B108 - test/controlled code uses tmpdir intentionally
        "/tmp/b.mp3"  # nosec B108 - test/controlled code uses tmpdir intentionally
    )


# ---------------------------------------------------------------------------
# _is_youtube_url
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", True),
        ("https://youtu.be/dQw4w9WgXcQ", True),
        ("http://youtube.com/watch?v=xyz", True),
        ("https://example.com/audio.mp3", False),
        ("not_a_url", False),
    ],
)
def test_is_youtube_url(url, expected):
    assert _is_youtube_url(url) == expected


# ---------------------------------------------------------------------------
# _validate_local_path
# ---------------------------------------------------------------------------


def test_validate_local_path_rejects_relative():
    with pytest.raises(ValueError, match="absolute"):
        _validate_local_path("relative/path.mp3")


def test_validate_local_path_rejects_missing_file():
    with pytest.raises(ValueError, match="not found"):
        _validate_local_path("/nonexistent/path/audio.mp3")


def test_validate_local_path_rejects_bad_extension():
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        with pytest.raises(ValueError, match="extension"):
            _validate_local_path(tmp_path)
    finally:
        os.unlink(tmp_path)


def test_validate_local_path_accepts_valid_mp3():
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        _validate_local_path(tmp_path)  # should not raise
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# AudioConnector.test_connection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connection_returns_false_when_no_sources():
    connector = AudioConnector(_make_config(sources=[]))
    assert await connector.test_connection() is False


@pytest.mark.asyncio
async def test_connection_returns_true_for_remote_url():
    connector = AudioConnector(_make_config(sources=["https://example.com/a.mp3"]))
    assert await connector.test_connection() is True


@pytest.mark.asyncio
async def test_connection_returns_true_for_existing_local_file():
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        connector = AudioConnector(_make_config(sources=[tmp_path]))
        assert await connector.test_connection() is True
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# AudioConnector.discover_sources
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discover_sources_returns_one_per_source():
    connector = AudioConnector(_make_config(sources=["https://youtu.be/abc", "https://example.com/x.mp3"]))
    sources = await connector.discover_sources()
    assert len(sources) == 2
    assert sources[0].source_id == _source_id_for("https://youtu.be/abc")


# ---------------------------------------------------------------------------
# AudioConnector.detect_changes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_changes_all_added():
    connector = AudioConnector(_make_config(sources=["https://youtu.be/abc"]))
    changes = await connector.detect_changes()
    assert len(changes) == 1
    assert changes[0].change_type == "added"


@pytest.mark.asyncio
async def test_detect_changes_incremental_still_returns_all():
    """Audio sources are immutable — incremental sync re-indexes them."""
    connector = AudioConnector(_make_config(sources=["https://youtu.be/abc"]))
    changes = await connector.detect_changes(since=datetime_now())
    assert len(changes) == 1


# ---------------------------------------------------------------------------
# AudioConnector.fetch_content — NPU path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_content_uses_npu_when_available():
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        connector = AudioConnector(_make_config(sources=[tmp_path]))
        source_id = _source_id_for(tmp_path)

        with patch(
            "knowledge.connectors.audio_connector._transcribe_with_npu",
            new=AsyncMock(return_value="NPU transcript text"),
        ):
            result = await connector.fetch_content(source_id)

        assert result is not None
        assert result.content == "NPU transcript text"
        assert result.metadata["type"] == "audio_transcript"
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# AudioConnector.fetch_content — CPU fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_content_falls_back_to_cpu_whisper():
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        connector = AudioConnector(_make_config(sources=[tmp_path]))
        source_id = _source_id_for(tmp_path)

        with (
            patch(
                "knowledge.connectors.audio_connector._transcribe_with_npu",
                new=AsyncMock(return_value=None),  # NPU unavailable
            ),
            patch(
                "knowledge.connectors.audio_connector._transcribe_with_whisper_cpu",
                return_value="CPU fallback transcript",
            ),
        ):
            result = await connector.fetch_content(source_id)

        assert result is not None
        assert result.content == "CPU fallback transcript"
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# AudioConnector.fetch_content — unknown source_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_content_returns_none_for_unknown_source_id():
    connector = AudioConnector(_make_config(sources=[]))
    result = await connector.fetch_content("deadbeef" * 4)
    assert result is None


# ---------------------------------------------------------------------------
# get_audio_pipeline_config
# ---------------------------------------------------------------------------


def test_audio_pipeline_config_has_transcribe_audio_first():
    cfg = get_audio_pipeline_config()
    assert cfg["name"] == "audio_knowledge_enrichment"
    first_task = cfg["extract"][0]
    assert first_task["task"] == "transcribe_audio"


def test_audio_pipeline_config_is_deep_copy():
    cfg1 = get_audio_pipeline_config()
    cfg2 = get_audio_pipeline_config()
    cfg1["extract"].append({"task": "extra", "params": {}})
    assert len(cfg2["extract"]) == 4  # original unmodified
