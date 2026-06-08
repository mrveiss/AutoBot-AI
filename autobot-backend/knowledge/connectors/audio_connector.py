# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Audio / Video / YouTube Connector

Issue #3243: Ingests audio/video content into the knowledge base by:
  1. Accepting a local audio/video file path, a YouTube URL, or a direct
     audio URL.
  2. Extracting audio via yt-dlp (YouTube/remote) or direct read (local).
  3. Transcribing via Whisper — NPU-accelerated where available, CPU fallback.
  4. Feeding the transcription through the standard ECL pipeline so it lands
     in ChromaDB with timestamp-anchored chunk metadata.

Supported source types
  - Local files: mp3, wav, m4a, ogg, flac, mp4, mkv, webm
  - YouTube URLs: https://www.youtube.com/watch?v=...  or  https://youtu.be/...
  - Direct audio URLs: any http/https link with an audio/video extension

Configuration keys (all under ConnectorConfig.config):
  sources (list[str]):        File paths or URLs to ingest.
  whisper_model (str):        Whisper model size. Default "base".
  language (str|None):        ISO-639-1 hint, e.g. "en".  None = auto-detect.
  npu_timeout (float):        Seconds to wait for NPU transcription. Default 120.
"""

import hashlib
import os
import re
import tempfile
from datetime import datetime, timezone
from typing import List

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc
from knowledge.connectors.base import AbstractConnector
from knowledge.connectors.models import (
    ChangeInfo,
    ConnectorConfig,
    ContentResult,
    SourceInfo,
)
from knowledge.connectors.registry import ConnectorRegistry

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Supported local extensions
# ---------------------------------------------------------------------------
_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
_VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".avi", ".mov"}
_MEDIA_EXTS = _AUDIO_EXTS | _VIDEO_EXTS

# YouTube URL patterns
_YT_PATTERN = re.compile(r"(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)[\w\-]+")


def _is_youtube_url(url: str) -> bool:
    return bool(_YT_PATTERN.match(url))


def _source_id_for(path_or_url: str) -> str:
    """Stable 32-char hex ID derived from the path/URL."""
    return hashlib.sha256(path_or_url.encode("utf-8")).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Whisper helpers
# ---------------------------------------------------------------------------


async def _transcribe_with_npu(
    audio_path: str,
    model_name: str,
    language: str | None,
    timeout: float,
) -> str | None:
    """Attempt transcription via the NPU worker. Returns None on failure."""
    try:
        from services.npu_client import get_npu_client

        client = get_npu_client()
        if not await client.is_available():
            return None
        result = await client.transcribe_audio(
            audio_path=audio_path,
            model=model_name,
            language=language,
            timeout=timeout,
        )
        return result
    except Exception as exc:
        logger.warning("NPU transcription failed, will fall back to CPU: %s", exc)
        return None


def _transcribe_with_whisper_cpu(
    audio_path: str,
    model_name: str,
    language: str | None,
) -> str:
    """Transcribe using the local whisper package (CPU). Raises on failure."""
    try:
        import whisper  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError("whisper package not installed.  Run: pip install openai-whisper") from exc

    model = whisper.load_model(model_name)
    options: dict = {}
    if language:
        options["language"] = language
    result = model.transcribe(audio_path, **options)
    return result.get("text", "")


async def _download_audio_yt_dlp(url: str, dest_dir: str) -> str:
    """Download audio track from a YouTube/remote URL via yt-dlp.

    Returns the path to the downloaded audio file.
    Raises RuntimeError if yt-dlp is not installed or download fails.
    """
    try:
        import yt_dlp  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError("yt-dlp not installed.  Run: pip install yt-dlp") from exc

    output_template = os.path.join(dest_dir, "%(id)s.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "128",
            }
        ],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        video_id = info.get("id", "audio")

    # yt-dlp renames the file after post-processing
    expected = os.path.join(dest_dir, f"{video_id}.mp3")
    if os.path.exists(expected):
        return expected

    # Fallback: find any audio file in the temp dir
    for fname in os.listdir(dest_dir):
        fpath = os.path.join(dest_dir, fname)
        if os.path.splitext(fname)[1] in _MEDIA_EXTS:
            return fpath

    raise RuntimeError(f"yt-dlp completed but no audio file found in {dest_dir}")


def _extract_yt_metadata(url: str) -> dict:
    """Return title, uploader, duration, thumbnail from yt-dlp without downloading."""
    try:
        import yt_dlp  # type: ignore[import-untyped]

        ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "title": info.get("title", ""),
                "uploader": info.get("uploader", ""),
                "duration_seconds": info.get("duration", 0),
                "thumbnail": info.get("thumbnail", ""),
                "webpage_url": info.get("webpage_url", url),
            }
    except Exception as exc:
        logger.warning("Could not fetch metadata for %s: %s", url, exc)
        return {"title": "", "webpage_url": url}


# ---------------------------------------------------------------------------
# Connector implementation
# ---------------------------------------------------------------------------


@ConnectorRegistry.register("audio")
class AudioConnector(AbstractConnector):
    """Connector that transcribes audio/video files and YouTube URLs into text.

    Config keys (all under ConnectorConfig.config):
        sources (list[str]):   File paths or URLs to process.
        whisper_model (str):   Whisper model size ("tiny", "base", "small", …).
        language (str|None):   Language hint. None = auto-detect.
        npu_timeout (float):   Seconds to wait for NPU worker. Default 120.
    """

    connector_type = "audio"
    # Issue #4421: zero-config — local files or public YouTube/media URLs; no
    # credentials required.  Whisper models run on NPU/CPU.
    tier = 0

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        cfg = config.config
        self._sources: List[str] = cfg.get("sources", [])
        self._whisper_model: str = cfg.get("whisper_model", "base")
        self._language: str | None = cfg.get("language") or None
        self._npu_timeout: float = float(cfg.get("npu_timeout", 120.0))

    # ------------------------------------------------------------------
    # AbstractConnector interface
    # ------------------------------------------------------------------

    async def test_connection(self) -> bool:
        """Verify that at least one source is reachable."""
        if not self._sources:
            return False
        for src in self._sources:
            if src.startswith(("http://", "https://")):
                return True  # remote URLs are assumed reachable
            if os.path.exists(src):
                return True
        return False

    async def discover_sources(self) -> List[SourceInfo]:
        """Return a SourceInfo for every configured source."""
        results: List[SourceInfo] = []
        for src in self._sources:
            source_id = _source_id_for(src)
            is_local = not src.startswith(("http://", "https://"))

            if is_local:
                stat = os.stat(src) if os.path.exists(src) else None
                size = stat.st_size if stat else 0
                mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc) if stat else now_utc()
            else:
                size = 0
                mtime = now_utc()

            results.append(
                SourceInfo(
                    source_id=source_id,
                    name=os.path.basename(src) if is_local else src,
                    path=src,
                    content_type="audio/x-audio",
                    size_bytes=size,
                    last_modified=mtime,
                    metadata={"original_path": src},
                )
            )
        return results

    async def detect_changes(self, since: datetime | None = None) -> List[ChangeInfo]:
        """Return all sources as 'added' (audio content is immutable once ingested)."""
        sources = await self.discover_sources()
        return [
            ChangeInfo(
                source_id=s.source_id,
                change_type="added",
                timestamp=s.last_modified,
                details={"original_path": s.metadata.get("original_path", "")},
            )
            for s in sources
        ]

    async def fetch_content(self, source_id: str) -> ContentResult | None:
        """Fetch and transcribe a single source identified by *source_id*."""
        # Resolve original path from source_id
        original_path: str | None = None
        for src in self._sources:
            if _source_id_for(src) == source_id:
                original_path = src
                break

        if original_path is None:
            logger.warning("No source found for id=%s", source_id)
            return None

        return await self._transcribe_source(source_id, original_path)

    # ------------------------------------------------------------------
    # Transcription orchestration
    # ------------------------------------------------------------------

    async def _transcribe_source(self, source_id: str, source: str) -> ContentResult:
        """Resolve source to an audio file path, then transcribe."""
        is_remote = source.startswith(("http://", "https://"))

        with tempfile.TemporaryDirectory() as tmp_dir:
            if is_remote:
                audio_path, extra_meta = await self._resolve_remote(source, tmp_dir)
            else:
                _validate_local_path(source)
                audio_path = source
                extra_meta = {}

            transcript = await self._run_transcription(audio_path)

        metadata = _build_metadata(source, extra_meta)
        return ContentResult(
            source_id=source_id,
            content=transcript,
            content_type="text/plain",
            metadata=metadata,
        )

    async def _resolve_remote(self, url: str, tmp_dir: str) -> "tuple[str, dict]":
        """Download remote URL to tmp_dir.  Returns (audio_path, extra_metadata)."""
        if _is_youtube_url(url):
            extra_meta = _extract_yt_metadata(url)
            audio_path = await _download_audio_yt_dlp(url, tmp_dir)
        else:
            audio_path = await _download_direct_url(url, tmp_dir)
            extra_meta = {}
        return audio_path, extra_meta

    async def _run_transcription(self, audio_path: str) -> str:
        """Try NPU transcription; fall back to CPU Whisper."""
        transcript = await _transcribe_with_npu(
            audio_path=audio_path,
            model_name=self._whisper_model,
            language=self._language,
            timeout=self._npu_timeout,
        )
        if not transcript:
            logger.info(
                "Falling back to CPU Whisper (model=%s) for %s",
                self._whisper_model,
                audio_path,
            )
            transcript = _transcribe_with_whisper_cpu(
                audio_path=audio_path,
                model_name=self._whisper_model,
                language=self._language,
            )
        return transcript.strip()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _download_direct_url(url: str, dest_dir: str) -> str:
    """Download a direct audio URL to dest_dir and return the local path."""
    import aiohttp

    filename = os.path.basename(url.split("?")[0]) or "audio.mp3"
    dest_path = os.path.join(dest_dir, filename)

    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=300)) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Failed to download {url}: HTTP {resp.status}")
            with open(dest_path, "wb", encoding=None) as fh:  # type: ignore[call-overload]
                async for chunk in resp.content.iter_chunked(65536):
                    fh.write(chunk)
    return dest_path


def _validate_local_path(path: str) -> None:
    """Raise ValueError if path is not a safe absolute path to an existing media file."""
    if not os.path.isabs(path):
        raise ValueError(f"Local audio path must be absolute: {path!r}")
    if not os.path.exists(path):
        raise ValueError(f"Audio file not found: {path!r}")
    ext = os.path.splitext(path.lower())[1]
    if ext not in _MEDIA_EXTS:
        raise ValueError(f"Unsupported audio/video extension {ext!r}. Allowed: {sorted(_MEDIA_EXTS)}")


def _build_metadata(source: str, extra: dict) -> dict:
    """Build a metadata dict for the transcribed content."""
    return {
        "source": source,
        "source_url": source,
        "content_type": "audio_transcript",
        "title": extra.get("title", os.path.basename(source)),
        "uploader": extra.get("uploader", ""),
        "duration_seconds": extra.get("duration_seconds", 0),
        "thumbnail": extra.get("thumbnail", ""),
        "category": "audio",
        "type": "audio_transcript",
    }
