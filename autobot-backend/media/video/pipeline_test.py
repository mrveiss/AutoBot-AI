# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Video Pipeline Tests
# Issue #932: Implement actual video processing

"""Unit tests for VideoPipeline."""

import base64
from unittest.mock import MagicMock, patch

import pytest
from media.core.types import MediaInput, MediaType, ProcessingIntent
from media.video.pipeline import VideoPipeline


def _make_input(data, mime_type="video/mp4"):
    return MediaInput(
        media_id="test-video",
        media_type=MediaType.VIDEO,
        intent=ProcessingIntent.ANALYSIS,
        data=data,
        mime_type=mime_type,
        metadata={"source": "test"},
    )


# Minimal MP4 ftyp box (4 bytes size + 'ftyp' + ...)
_FAKE_MP4_MAGIC = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 8
_FAKE_MKV_MAGIC = b"\x1aE\xdf\xa3" + b"\x00" * 20
_FAKE_AVI_MAGIC = b"RIFF" + b"\x00" * 20


class TestVideoPipelineDecoding:
    """Tests for _decode_input."""

    def test_bytes_passthrough(self):
        pipe = VideoPipeline()
        raw = b"video bytes"
        assert pipe._decode_input(raw) == raw

    def test_base64_string(self):
        pipe = VideoPipeline()
        raw = b"video data"
        encoded = base64.b64encode(raw).decode()
        assert pipe._decode_input(encoded) == raw

    def test_unsupported_type_raises(self):
        pipe = VideoPipeline()
        with pytest.raises(ValueError, match="Unsupported"):
            pipe._decode_input(123)


class TestVideoPipelineFormatDetection:
    """Tests for _detect_format."""

    def test_mp4_by_magic(self):
        pipe = VideoPipeline()
        assert pipe._detect_format(_FAKE_MP4_MAGIC, "") == "mp4"

    def test_mp4_ftyp_at_offset_4(self):
        pipe = VideoPipeline()
        data = b"\x00\x00\x00\x20" + b"ftyp" + b"\x00" * 10
        assert pipe._detect_format(data, "") == "mp4"

    def test_mkv_by_magic(self):
        pipe = VideoPipeline()
        assert pipe._detect_format(_FAKE_MKV_MAGIC, "") == "mkv"

    def test_avi_by_magic(self):
        pipe = VideoPipeline()
        assert pipe._detect_format(_FAKE_AVI_MAGIC, "") == "avi"

    def test_mp4_by_mime(self):
        pipe = VideoPipeline()
        assert pipe._detect_format(b"garbage", "video/mp4") == "mp4"

    def test_webm_by_mime(self):
        pipe = VideoPipeline()
        assert pipe._detect_format(b"garbage", "video/webm") == "webm"

    def test_unknown_format(self):
        pipe = VideoPipeline()
        assert pipe._detect_format(b"random data", "") == "unknown"


class TestVideoPipelineSuffix:
    """Tests for _suffix_from_mime."""

    def test_known_mimes(self):
        pipe = VideoPipeline()
        assert pipe._suffix_from_mime("video/mp4") == ".mp4"
        assert pipe._suffix_from_mime("video/x-msvideo") == ".avi"
        assert pipe._suffix_from_mime("video/webm") == ".webm"
        assert pipe._suffix_from_mime("video/quicktime") == ".mov"

    def test_unknown_defaults_to_mp4(self):
        pipe = VideoPipeline()
        assert pipe._suffix_from_mime("video/unknown") == ".mp4"
        assert pipe._suffix_from_mime("") == ".mp4"


class TestVideoPipelineFormatOnlyResult:
    """Tests for _format_only_result fallback."""

    def test_known_format_gives_partial_status(self):
        pipe = VideoPipeline()
        result = pipe._format_only_result("mp4", _FAKE_MP4_MAGIC, "video/mp4", {})
        assert result["format"] == "mp4"
        assert result["processing_status"] == "partial"
        assert result["confidence"] == 0.3
        assert result["frames_processed"] == 0

    def test_unknown_format_gives_unavailable(self):
        pipe = VideoPipeline()
        result = pipe._format_only_result("unknown", b"junk", "", {})
        assert result["processing_status"] == "unavailable"
        assert result["confidence"] == 0.0

    def test_includes_file_size(self):
        pipe = VideoPipeline()
        data = b"x" * 1024
        result = pipe._format_only_result("mp4", data, "video/mp4", {})
        assert result["file_size_bytes"] == 1024


class TestVideoPipelineCv2:
    """Tests for cv2 extraction path."""

    def test_read_video_info(self):
        pipe = VideoPipeline()
        mock_cap = MagicMock()
        mock_cap.get = lambda prop: {
            5: 30.0,  # CAP_PROP_FPS
            7: 900,  # CAP_PROP_FRAME_COUNT
            3: 1920.0,  # CAP_PROP_FRAME_WIDTH
            4: 1080.0,  # CAP_PROP_FRAME_HEIGHT
        }.get(prop, 0.0)

        with patch("media.video.pipeline.cv2.CAP_PROP_FPS", 5), patch(
            "media.video.pipeline.cv2.CAP_PROP_FRAME_COUNT", 7
        ), patch("media.video.pipeline.cv2.CAP_PROP_FRAME_WIDTH", 3), patch(
            "media.video.pipeline.cv2.CAP_PROP_FRAME_HEIGHT", 4
        ):
            info = pipe._read_video_info(mock_cap)

        assert info["fps"] == 30.0
        assert info["frame_count"] == 900
        assert info["resolution"] == "1920x1080"
        assert info["duration"] == pytest.approx(30.0)

    def test_encode_frame_returns_base64(self):
        try:
            import cv2  # noqa: F401
            import numpy as np
        except ImportError:
            pytest.skip("opencv-python not installed")

        pipe = VideoPipeline()
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        encoded = pipe._encode_frame(frame)
        assert encoded is not None
        decoded = base64.b64decode(encoded)
        assert len(decoded) > 0

    def test_extract_with_cv2_calls_release(self):
        """cv2.VideoCapture.release() must be called to avoid resource leak."""
        try:
            import cv2  # noqa: F401
        except ImportError:
            pytest.skip("opencv-python not installed")

        pipe = VideoPipeline()
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get = MagicMock(return_value=0.0)
        mock_cap.read = MagicMock(return_value=(False, None))

        deleted = []

        with patch(
            "media.video.pipeline.cv2.VideoCapture", return_value=mock_cap
        ), patch("os.unlink", side_effect=lambda p: deleted.append(p)):
            pipe._extract_with_cv2(_FAKE_MP4_MAGIC, "video/mp4", "mp4", {})

        mock_cap.release.assert_called_once()
        assert len(deleted) == 1  # temp file cleaned up


class TestVideoPipelineAsync:
    """End-to-end async processing tests."""

    @pytest.mark.asyncio
    async def test_process_impl_cv2_unavailable(self):
        pipe = VideoPipeline()
        media_input = _make_input(_FAKE_MP4_MAGIC)

        with patch("media.video.pipeline._CV2_AVAILABLE", False):
            result = await pipe._process_impl(media_input)

        assert result.success is True
        assert result.result_data["type"] == "video_analysis"
        assert result.result_data["format"] == "mp4"
        assert result.result_data["processing_method"] == "format_detection_only"

    @pytest.mark.asyncio
    async def test_process_impl_cv2_exception_falls_back(self):
        pipe = VideoPipeline()
        media_input = _make_input(_FAKE_MP4_MAGIC)

        with patch("media.video.pipeline._CV2_AVAILABLE", True), patch.object(
            pipe, "_extract_with_cv2", side_effect=RuntimeError("cv2 error")
        ):
            result = await pipe._process_impl(media_input)

        assert result.success is True
        assert result.result_data["processing_method"] == "format_detection_only"
