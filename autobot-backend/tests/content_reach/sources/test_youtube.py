# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for content_reach.sources.youtube (YtDlpCaptionBackend, build_youtube_chain)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from content_reach.base import BackendError, ContentRequest
from source_attribution import SourceType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_VTT = """\
WEBVTT

00:00:00.000 --> 00:00:03.000
Hello world

00:00:03.000 --> 00:00:06.000
This is a test caption.
"""

_FAKE_JSON3 = """\
{
  "events": [
    {"segs": [{"utf8": "Hello world"}]},
    {"segs": [{"utf8": "This is a test caption."}]}
  ]
}
"""

_FAKE_SRV1 = """\
<?xml version="1.0" encoding="utf-8" ?>
<transcript>
  <text start="0" dur="3">Hello &amp; welcome</text>
  <text start="3" dur="3">This is SRV1.</text>
</transcript>
"""

_FAKE_INFO = {
    "title": "Test Video",
    "duration": 120,
    "subtitles": {
        "en": [
            {"ext": "vtt", "url": "https://fake-caption-host/captions.vtt"},
        ]
    },
    "automatic_captions": {},
}

_FAKE_INFO_AUTO = {
    "title": "Auto Video",
    "duration": 60,
    "subtitles": {},
    "automatic_captions": {
        "en": [
            {"ext": "json3", "url": "https://fake-caption-host/auto.json3"},
            {"ext": "vtt", "url": "https://fake-caption-host/auto.vtt"},
        ]
    },
}

_FAKE_INFO_SRV1 = {
    "title": "SRV1 Video",
    "duration": 10,
    "subtitles": {
        "en": [
            {"ext": "srv1", "url": "https://fake-caption-host/captions.srv1"},
        ]
    },
    "automatic_captions": {},
}

_FAKE_INFO_NO_CAPTIONS = {
    "title": "No Captions",
    "duration": 30,
    "subtitles": {},
    "automatic_captions": {},
}


# ---------------------------------------------------------------------------
# YtDlpCaptionBackend — probe()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ytdlp_probe_true_when_importable():
    """probe() returns True when yt_dlp is importable (installed in this venv)."""
    yt_dlp = pytest.importorskip("yt_dlp")  # noqa: F841 — skip if absent
    from content_reach.sources.youtube import YtDlpCaptionBackend

    backend = YtDlpCaptionBackend()
    assert await backend.probe() is True


@pytest.mark.asyncio
async def test_ytdlp_probe_false_when_absent(monkeypatch):
    """probe() returns False when the lazy import helper raises ImportError."""
    from content_reach.sources import youtube as yt_mod

    monkeypatch.setattr(
        yt_mod,
        "_import_yt_dlp",
        lambda: (_ for _ in ()).throw(ImportError("no yt_dlp")),
    )

    from content_reach.sources.youtube import YtDlpCaptionBackend

    backend = YtDlpCaptionBackend()
    assert await backend.probe() is False


# ---------------------------------------------------------------------------
# YtDlpCaptionBackend — fetch(): happy path (subtitles["en"])
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ytdlp_fetch_maps_caption_text(monkeypatch):
    """fetch() returns ContentResult with captions text when subtitles["en"] present."""
    from content_reach.sources import youtube as yt_mod

    monkeypatch.setattr(yt_mod, "_ytdlp_extract_info", lambda url: _FAKE_INFO)

    mock_response = MagicMock()
    mock_response.text = _FAKE_VTT

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    from content_reach.sources.youtube import YtDlpCaptionBackend

    backend = YtDlpCaptionBackend(client=mock_client)
    request = ContentRequest(url="https://www.youtube.com/watch?v=test123")
    result = await backend.fetch(request)

    assert result.success is True
    assert result.backend_used == "yt_dlp"
    assert result.source_type == SourceType.YOUTUBE
    assert "Hello world" in result.text
    assert result.structured["title"] == "Test Video"
    assert result.structured["duration"] == 120
    assert result.url == "https://www.youtube.com/watch?v=test123"


@pytest.mark.asyncio
async def test_ytdlp_fetch_falls_back_to_automatic_captions(monkeypatch):
    """fetch() falls back to automatic_captions["en"] and parses json3 body correctly.

    _FAKE_INFO_AUTO exposes a json3 track first; the mock response body is valid
    json3 so the real _json3_to_text path is exercised (not the JSONDecodeError
    fallback that a VTT body would trigger).
    """
    from content_reach.sources import youtube as yt_mod

    monkeypatch.setattr(yt_mod, "_ytdlp_extract_info", lambda url: _FAKE_INFO_AUTO)

    mock_response = MagicMock()
    mock_response.text = _FAKE_JSON3  # json3 body matches the json3 track selected

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    from content_reach.sources.youtube import YtDlpCaptionBackend

    backend = YtDlpCaptionBackend(client=mock_client)
    request = ContentRequest(url="https://www.youtube.com/watch?v=auto456")
    result = await backend.fetch(request)

    assert result.success is True
    assert result.backend_used == "yt_dlp"
    assert result.structured["title"] == "Auto Video"
    assert "Hello world" in result.text
    assert "This is a test caption." in result.text


# ---------------------------------------------------------------------------
# YtDlpCaptionBackend — fetch(): no captions → BackendError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ytdlp_fetch_no_captions_raises(monkeypatch):
    """fetch() raises BackendError when no English captions are available."""
    from content_reach.sources import youtube as yt_mod

    monkeypatch.setattr(yt_mod, "_ytdlp_extract_info", lambda url: _FAKE_INFO_NO_CAPTIONS)

    from content_reach.sources.youtube import YtDlpCaptionBackend

    backend = YtDlpCaptionBackend()
    request = ContentRequest(url="https://www.youtube.com/watch?v=nocap789")
    with pytest.raises(BackendError):
        await backend.fetch(request)


# ---------------------------------------------------------------------------
# YtDlpCaptionBackend — fetch(): yt_dlp absent → BackendError in fetch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ytdlp_fetch_raises_when_yt_dlp_absent(monkeypatch):
    """fetch() raises BackendError (not ImportError) when yt_dlp is not installed."""
    from content_reach.sources import youtube as yt_mod

    monkeypatch.setattr(
        yt_mod,
        "_import_yt_dlp",
        lambda: (_ for _ in ()).throw(ImportError("no yt_dlp")),
    )

    from content_reach.sources.youtube import YtDlpCaptionBackend

    backend = YtDlpCaptionBackend()
    request = ContentRequest(url="https://www.youtube.com/watch?v=absent")
    with pytest.raises(BackendError, match="yt-dlp not installed"):
        await backend.fetch(request)


# ---------------------------------------------------------------------------
# YtDlpCaptionBackend — fetch(): httpx error → BackendError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ytdlp_fetch_httpx_error_raises_backend_error(monkeypatch):
    """fetch() wraps httpx.HTTPError into BackendError."""
    from content_reach.sources import youtube as yt_mod

    monkeypatch.setattr(yt_mod, "_ytdlp_extract_info", lambda url: _FAKE_INFO)

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(side_effect=httpx.HTTPError("connection failed"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    from content_reach.sources.youtube import YtDlpCaptionBackend

    backend = YtDlpCaptionBackend(client=mock_client)
    request = ContentRequest(url="https://www.youtube.com/watch?v=httperr")
    with pytest.raises(BackendError):
        await backend.fetch(request)


# ---------------------------------------------------------------------------
# build_youtube_chain()
# ---------------------------------------------------------------------------


def test_build_youtube_chain_order():
    """build_youtube_chain() returns chain with source_type YOUTUBE and backend ['yt_dlp']."""
    from content_reach.sources.youtube import build_youtube_chain

    chain = build_youtube_chain()
    assert chain.source == "youtube"
    assert chain.source_type == SourceType.YOUTUBE
    assert chain.backend_names() == ["yt_dlp"]


# ---------------------------------------------------------------------------
# _srv1_to_text unit test
# ---------------------------------------------------------------------------


def test_srv1_track_parsed():
    """_srv1_to_text extracts plain text from SRV1 XML, unescaping HTML entities."""
    from content_reach.sources.youtube import _srv1_to_text

    result = _srv1_to_text(_FAKE_SRV1)
    assert "Hello & welcome" in result
    assert "This is SRV1." in result


@pytest.mark.asyncio
async def test_ytdlp_fetch_srv1_track(monkeypatch):
    """fetch() selects an srv1 track and returns correctly decoded plain text."""
    from content_reach.sources import youtube as yt_mod

    monkeypatch.setattr(yt_mod, "_ytdlp_extract_info", lambda url: _FAKE_INFO_SRV1)

    mock_response = MagicMock()
    mock_response.text = _FAKE_SRV1

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    from content_reach.sources.youtube import YtDlpCaptionBackend

    backend = YtDlpCaptionBackend(client=mock_client)
    request = ContentRequest(url="https://www.youtube.com/watch?v=srv1test")
    result = await backend.fetch(request)

    assert result.success is True
    assert result.backend_used == "yt_dlp"
    assert result.structured["title"] == "SRV1 Video"
    assert "Hello & welcome" in result.text
    assert "This is SRV1." in result.text
