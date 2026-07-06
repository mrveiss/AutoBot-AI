# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""YouTube captions content source via yt-dlp (#10932).

Chain:
  1. YtDlpCaptionBackend — extracts English captions (subtitles or automatic)
     via yt-dlp, converts to plain text, returns ContentResult.
"""

from __future__ import annotations

import asyncio
import re

import httpx

from autobot_shared.logging_manager import get_logger
from content_reach.base import BackendError, ContentBackend, ContentRequest, ContentResult
from content_reach.chain import ContentSourceChain
from source_attribution import SourceReliability, SourceType

logger = get_logger(__name__)

# Module-level HTTP timeout constant (seconds).
_HTTP_TIMEOUT = 15.0

# yt-dlp options used for all caption extractions.
_YDL_OPTS: dict = {
    "skip_download": True,
    "writesubtitles": True,
    "writeautomaticsub": True,
    "subtitleslangs": ["en"],
    "quiet": True,
    "no_warnings": True,
}

# Caption formats we can parse to plain text, in preference order.
_PREFERRED_EXTS = ("json3", "srv1", "vtt")


def _import_yt_dlp():
    """Lazy import of yt_dlp; raises ImportError if not installed."""
    import yt_dlp as _yt_dlp

    return _yt_dlp


def _ytdlp_extract_info(url: str) -> dict:
    """Synchronous wrapper around YoutubeDL.extract_info.

    Module-level so tests can monkeypatch without hitting the network.
    """
    yt_dlp = _import_yt_dlp()
    with yt_dlp.YoutubeDL(_YDL_OPTS) as ydl:
        return ydl.extract_info(url, download=False)


def _vtt_to_text(vtt: str) -> str:
    """Convert WebVTT/SRV1 caption content to plain text lines."""
    # Strip WEBVTT header and timestamps; keep non-empty non-tag lines.
    lines = []
    for line in vtt.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("WEBVTT") or line.startswith("NOTE"):
            continue
        # Skip timestamp lines like "00:00:00.000 --> 00:00:03.000"
        if re.match(r"^\d{2}:\d{2}:\d{2}[.,]\d{3}\s+-->\s+", line):
            continue
        # Strip inline tags: <c>, </c>, <00:00:00.000>, etc.
        line = re.sub(r"<[^>]+>", "", line)
        if line:
            lines.append(line)
    return "\n".join(lines)


def _json3_to_text(raw: str) -> str:
    """Convert yt-dlp json3 caption format to plain text."""
    import json

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw

    parts = []
    for event in data.get("events", []):
        segs = event.get("segs")
        if not segs:
            continue
        segment_text = "".join(s.get("utf8", "") for s in segs).strip()
        if segment_text and segment_text != "\n":
            parts.append(segment_text)
    return "\n".join(parts)


def _caption_raw_to_text(raw: str, ext: str) -> str:
    """Convert raw caption file content to plain text based on extension."""
    if ext == "json3":
        return _json3_to_text(raw)
    # vtt and srv1 share the same timestamp-stripping logic.
    return _vtt_to_text(raw)


def _pick_caption_track(info: dict) -> tuple[str, str] | None:
    """Return (url, ext) for the best available English caption track, or None."""
    for source in ("subtitles", "automatic_captions"):
        tracks = info.get(source, {}).get("en", [])
        for ext in _PREFERRED_EXTS:
            for entry in tracks:
                if entry.get("ext") == ext and entry.get("url"):
                    return entry["url"], ext
    return None


class YtDlpCaptionBackend(ContentBackend):
    """YouTube captions backend using yt-dlp to extract English subtitle tracks.

    probe() returns True iff yt_dlp is importable.
    fetch() calls yt_dlp.YoutubeDL.extract_info in asyncio.to_thread (yt-dlp
    is synchronous), picks the best English caption track, GETs its URL via
    httpx, converts to plain text, and returns a ContentResult.

    Accepts an optional injected httpx.AsyncClient for testing.
    """

    name = "yt_dlp"
    source_type = SourceType.YOUTUBE

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def probe(self) -> bool:
        """Return True iff yt_dlp is importable."""
        try:
            _import_yt_dlp()
            return True
        except ImportError:
            logger.warning("YtDlpCaptionBackend: yt_dlp is not installed; backend unavailable")
            return False

    async def fetch(self, request: ContentRequest) -> ContentResult:
        """Extract captions from request.url via yt-dlp; raise BackendError on failure."""
        try:
            _import_yt_dlp()
        except ImportError:
            raise BackendError("yt-dlp not installed")

        info: dict = await asyncio.to_thread(_ytdlp_extract_info, request.url)

        track = _pick_caption_track(info)
        if track is None:
            logger.debug(
                "YtDlpCaptionBackend: no English captions found for %r",
                request.url,
            )
            raise BackendError(f"YtDlpCaptionBackend: no English captions for {request.url!r}")

        caption_url, ext = track

        try:
            if self._client is not None:
                response = await self._client.get(caption_url)
            else:
                async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                    response = await client.get(caption_url)
        except httpx.HTTPError as exc:
            logger.debug(
                "YtDlpCaptionBackend: HTTP error fetching caption track for %r: %s",
                request.url,
                exc,
            )
            raise BackendError(f"YtDlpCaptionBackend: HTTP error fetching captions: {exc}") from exc

        text = _caption_raw_to_text(response.text, ext)

        if not text.strip():
            logger.debug("YtDlpCaptionBackend: empty caption text for %r", request.url)
            raise BackendError(f"YtDlpCaptionBackend: empty captions for {request.url!r}")

        return ContentResult(
            success=True,
            source_type=self.source_type,
            backend_used=self.name,
            text=text,
            structured={
                "title": info.get("title"),
                "duration": info.get("duration"),
            },
            url=request.url,
            reliability=SourceReliability.MEDIUM,
        )


def build_youtube_chain() -> ContentSourceChain:
    """Build the YouTube caption chain: yt_dlp."""
    return ContentSourceChain(
        source="youtube",
        source_type=SourceType.YOUTUBE,
        backends=[YtDlpCaptionBackend()],
    )
