# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Video Processing Pipeline
# Issue #735: Organize media processing into dedicated pipelines
# Issue #932: Implement actual video processing

"""Video processing pipeline for video content."""

import asyncio
import base64
import logging
import os
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from media.core.pipeline import BasePipeline
from media.core.types import MediaInput, MediaType, ProcessingResult

# Optional: OpenCV for frame extraction and video metadata
try:
    import cv2

    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False

logger = logging.getLogger(__name__)

# Magic bytes for common video formats
_VIDEO_MAGIC: List[Tuple[bytes, str]] = [
    (b"\x00\x00\x00\x18ftyp", "mp4"),
    (b"\x00\x00\x00\x1cftyp", "mp4"),
    (b"\x00\x00\x00 ftyp", "mp4"),
    (b"ftyp", "mp4"),  # at offset 4 — checked separately
    (b"\x1aE\xdf\xa3", "mkv"),
    (b"RIFF", "avi"),
    (b"OggS", "ogv"),
    (b"\x1fG\xef\xff", "ts"),
    (b"\x47", "ts"),  # MPEG-TS sync byte
]

_MIME_TO_FORMAT: Dict[str, str] = {
    "video/mp4": "mp4",
    "video/x-msvideo": "avi",
    "video/x-matroska": "mkv",
    "video/webm": "webm",
    "video/ogg": "ogv",
    "video/mpeg": "mpeg",
    "video/quicktime": "mov",
    "video/3gpp": "3gp",
    "video/x-flv": "flv",
}

_MIME_TO_EXT: Dict[str, str] = {
    "video/mp4": ".mp4",
    "video/x-msvideo": ".avi",
    "video/x-matroska": ".mkv",
    "video/webm": ".webm",
    "video/ogg": ".ogv",
    "video/mpeg": ".mpeg",
    "video/quicktime": ".mov",
    "video/3gpp": ".3gp",
    "video/x-flv": ".flv",
}

# Maximum frames to extract for analysis
_MAX_FRAMES = 5


class VideoPipeline(BasePipeline):
    """Pipeline for processing video content."""

    def __init__(self):
        """Initialize video processing pipeline."""
        super().__init__(
            pipeline_name="video",
            supported_types=[MediaType.VIDEO],
        )

    async def _process_impl(self, media_input: MediaInput) -> ProcessingResult:
        """Process video content."""
        result_data = await self._process_video(media_input)
        confidence = self._calculate_confidence(result_data)

        return ProcessingResult(
            result_id=f"video_{media_input.media_id}",
            media_id=media_input.media_id,
            media_type=media_input.media_type,
            intent=media_input.intent,
            success=True,
            confidence=confidence,
            result_data=result_data,
            processing_time=0.0,  # Set by BasePipeline
        )

    async def _process_video(self, media_input: MediaInput) -> Dict[str, Any]:
        """Detect video format, extract metadata and frames via cv2 if available."""
        raw_bytes = self._decode_input(media_input.data)
        mime = (media_input.mime_type or "").lower()
        fmt = self._detect_format(raw_bytes, mime)

        if not _CV2_AVAILABLE:
            return self._format_only_result(fmt, raw_bytes, mime, media_input.metadata)

        try:
            result = await asyncio.to_thread(
                self._extract_with_cv2, raw_bytes, mime, fmt, media_input.metadata
            )
            return result
        except Exception as exc:
            logger.warning("cv2 video processing failed: %s", exc)
            return self._format_only_result(fmt, raw_bytes, mime, media_input.metadata)

    # ------------------------------------------------------------------
    # Input decoding helpers
    # ------------------------------------------------------------------

    def _decode_input(self, data: Any) -> bytes:
        """Normalize input data to raw bytes."""
        if isinstance(data, bytes):
            return data
        if isinstance(data, str):
            try:
                return base64.b64decode(data)
            except Exception:
                with open(data, "rb") as fh:
                    return fh.read()
        raise ValueError(f"Unsupported video data type: {type(data)}")

    def _detect_format(self, raw_bytes: bytes, mime: str) -> str:
        """Detect video format from magic bytes or MIME type."""
        # Check magic bytes at offset 0
        for magic, fmt in _VIDEO_MAGIC:
            if raw_bytes[: len(magic)] == magic:
                return fmt
        # MP4/MOV stores 'ftyp' at offset 4
        if len(raw_bytes) >= 8 and raw_bytes[4:8] == b"ftyp":
            return "mp4"
        # Fall back to MIME type
        if mime in _MIME_TO_FORMAT:
            return _MIME_TO_FORMAT[mime]
        return "unknown"

    def _suffix_from_mime(self, mime: str) -> str:
        """Map MIME type to file extension for temp file."""
        return _MIME_TO_EXT.get(mime, ".mp4")

    # ------------------------------------------------------------------
    # cv2-based extraction (blocking — run via asyncio.to_thread)
    # ------------------------------------------------------------------

    def _extract_with_cv2(
        self, raw_bytes: bytes, mime: str, fmt: str, metadata: Dict
    ) -> Dict[str, Any]:
        """Extract video metadata and sample frames using OpenCV."""
        suffix = self._suffix_from_mime(mime)
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(raw_bytes)
            tmp_path = tmp.name

        try:
            cap = cv2.VideoCapture(tmp_path)
            if not cap.isOpened():
                raise RuntimeError(f"cv2 could not open video file ({fmt})")

            video_info = self._read_video_info(cap)
            frames = self._extract_sample_frames(cap, video_info["frame_count"])
            cap.release()

            return {
                "type": "video_analysis",
                "format": fmt,
                "processing_method": "cv2",
                "frames_processed": len(frames),
                "frame_thumbnails": frames,
                "confidence": 0.85,
                "metadata": metadata,
                **video_info,
            }
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _read_video_info(self, cap: Any) -> Dict[str, Any]:
        """Extract duration, FPS, resolution, and frame count from cv2 capture."""
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        duration = (frame_count / fps) if fps > 0 else 0.0
        return {
            "duration": round(duration, 3),
            "fps": round(fps, 2),
            "frame_count": frame_count,
            "resolution": f"{width}x{height}" if width and height else "unknown",
            "width": width,
            "height": height,
        }

    def _extract_sample_frames(self, cap: Any, total_frames: int) -> List[str]:
        """Extract up to _MAX_FRAMES evenly-spaced frames as base64 JPEG."""
        if total_frames <= 0:
            return []

        step = max(1, total_frames // _MAX_FRAMES)
        frames: List[str] = []

        for i in range(_MAX_FRAMES):
            frame_pos = i * step
            if frame_pos >= total_frames:
                break
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
            ret, frame = cap.read()
            if not ret:
                continue
            encoded = self._encode_frame(frame)
            if encoded:
                frames.append(encoded)

        return frames

    def _encode_frame(self, frame: Any) -> Optional[str]:
        """Encode a cv2 frame to a base64 JPEG string."""
        try:
            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
            return base64.b64encode(buf.tobytes()).decode("ascii")
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Fallback result (no cv2)
    # ------------------------------------------------------------------

    def _format_only_result(
        self, fmt: str, raw_bytes: bytes, mime: str, metadata: Dict
    ) -> Dict[str, Any]:
        """Return format-detected result when cv2 is unavailable."""
        logger.info("cv2 unavailable; returning format-only result for %s video", fmt)
        return {
            "type": "video_analysis",
            "format": fmt,
            "processing_method": "format_detection_only",
            "frames_processed": 0,
            "frame_thumbnails": [],
            "duration": 0.0,
            "fps": 0.0,
            "frame_count": 0,
            "resolution": "unknown",
            "file_size_bytes": len(raw_bytes),
            "processing_status": "partial" if fmt != "unknown" else "unavailable",
            "unavailability_reason": (
                "opencv-python not installed. Run: pip install opencv-python"
            ),
            "confidence": 0.3 if fmt != "unknown" else 0.0,
            "metadata": metadata,
        }

    def _calculate_confidence(self, result_data: Dict[str, Any]) -> float:
        """Calculate confidence score from result data."""
        return result_data.get("confidence", 0.5)
