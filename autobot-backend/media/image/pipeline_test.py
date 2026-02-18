# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Image Pipeline Tests
# Issue #932: Implement actual image processing

"""Unit tests for ImagePipeline."""

import base64
import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from media.core.types import MediaInput, MediaType, ProcessingIntent
from media.image.pipeline import ImagePipeline


def _make_input(data, mime_type="image/jpeg"):
    return MediaInput(
        media_id="test-img",
        media_type=MediaType.IMAGE,
        intent=ProcessingIntent.ANALYSIS,
        data=data,
        mime_type=mime_type,
        metadata={"source": "test"},
    )


def _make_minimal_jpeg() -> bytes:
    """Return a 1x1 red pixel JPEG as bytes."""
    try:
        from PIL import Image

        buf = io.BytesIO()
        img = Image.new("RGB", (1, 1), color=(255, 0, 0))
        img.save(buf, format="JPEG")
        return buf.getvalue()
    except ImportError:
        # Return a tiny but valid JPEG header
        return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"


class TestImagePipelineDecoding:
    """Tests for _decode_input."""

    def test_bytes_passthrough(self):
        pipe = ImagePipeline()
        raw = b"image bytes"
        assert pipe._decode_input(raw) == raw

    def test_base64_string(self):
        pipe = ImagePipeline()
        raw = b"image data"
        encoded = base64.b64encode(raw).decode()
        assert pipe._decode_input(encoded) == raw

    def test_pil_image_passthrough(self):
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not installed")

        pipe = ImagePipeline()
        img = Image.new("RGB", (2, 2), color=(0, 255, 0))
        result = pipe._decode_input(img)
        assert isinstance(result, bytes)

    def test_unsupported_type_raises(self):
        pipe = ImagePipeline()
        with pytest.raises(ValueError, match="Unsupported"):
            pipe._decode_input(999)


class TestImagePipelineMetadata:
    """Tests for _extract_basic_metadata."""

    def test_basic_fields(self):
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not installed")

        pipe = ImagePipeline()
        img = Image.new("RGB", (100, 200))
        meta = pipe._extract_basic_metadata(img)
        assert meta["width"] == 100
        assert meta["height"] == 200
        assert meta["mode"] == "RGB"

    def test_no_exif_handled_gracefully(self):
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not installed")

        pipe = ImagePipeline()
        img = Image.new("RGBA", (10, 10))
        meta = pipe._extract_basic_metadata(img)
        assert "exif" not in meta  # No EXIF on synthetic images


class TestImagePipelineUnavailable:
    """Tests for unavailability path."""

    def test_unavailable_result_structure(self):
        pipe = ImagePipeline()
        result = pipe._unavailable_result(
            "PIL not installed. Run: pip install Pillow", {}
        )
        assert result["type"] == "image_analysis"
        assert result["processing_status"] == "unavailable"
        assert result["confidence"] == 0.0
        assert "PIL not installed" in result["unavailability_reason"]

    @pytest.mark.asyncio
    async def test_process_image_returns_unavailable_without_pil(self):
        pipe = ImagePipeline()
        media_input = _make_input(b"fake image")

        with patch("media.image.pipeline._PIL_AVAILABLE", False):
            result = await pipe._process_image(media_input)

        assert result["processing_status"] == "unavailable"
        assert result["confidence"] == 0.0


class TestImagePipelinePilOnly:
    """Tests for PIL-only (no VisionProcessor) path."""

    @pytest.mark.asyncio
    async def test_pil_metadata_result(self):
        try:
            import PIL  # noqa: F401
        except ImportError:
            pytest.skip("Pillow not installed")

        pipe = ImagePipeline()
        img_bytes = _make_minimal_jpeg()
        media_input = _make_input(img_bytes)

        with patch("media.image.pipeline._VISION_PROCESSOR_AVAILABLE", False), patch(
            "media.image.pipeline._vision_processor", None
        ):
            result = await pipe._process_image(media_input)

        assert result["type"] == "image_analysis"
        assert result["processing_method"] == "pil_metadata_only"
        assert result["width"] >= 1
        assert result["height"] >= 1
        assert result["confidence"] == 0.7


class TestImagePipelineVisionProcessor:
    """Tests for VisionProcessor delegation path."""

    @pytest.mark.asyncio
    async def test_delegates_to_vision_processor(self):
        try:
            import PIL  # noqa: F401
        except ImportError:
            pytest.skip("Pillow not installed")

        pipe = ImagePipeline()
        img_bytes = _make_minimal_jpeg()
        media_input = _make_input(img_bytes)

        mock_vp_result = MagicMock()
        mock_vp_result.confidence = 0.95
        mock_vp_result.result_data = {
            "elements_detected": ["button"],
            "text_detected": "hello",
            "caption": "a red square",
        }

        mock_vp = AsyncMock()
        mock_vp.process = AsyncMock(return_value=mock_vp_result)

        mock_mm_input = MagicMock()

        with patch("media.image.pipeline._PIL_AVAILABLE", True), patch(
            "media.image.pipeline._VISION_PROCESSOR_AVAILABLE", True
        ), patch("media.image.pipeline._vision_processor", mock_vp), patch(
            "media.image.pipeline.MultiModalInput", return_value=mock_mm_input
        ):
            result = await pipe._process_image(media_input)

        assert result["processing_method"] == "vision_processor"
        assert result["confidence"] == 0.95
        assert "button" in result["elements_detected"]
        assert result["caption"] == "a red square"

    @pytest.mark.asyncio
    async def test_falls_back_to_pil_on_vp_error(self):
        try:
            import PIL  # noqa: F401
        except ImportError:
            pytest.skip("Pillow not installed")

        pipe = ImagePipeline()
        img_bytes = _make_minimal_jpeg()
        media_input = _make_input(img_bytes)

        mock_vp = AsyncMock()
        mock_vp.process = AsyncMock(side_effect=RuntimeError("GPU unavailable"))

        with patch("media.image.pipeline._PIL_AVAILABLE", True), patch(
            "media.image.pipeline._VISION_PROCESSOR_AVAILABLE", True
        ), patch("media.image.pipeline._vision_processor", mock_vp), patch(
            "media.image.pipeline.MultiModalInput", return_value=MagicMock()
        ):
            result = await pipe._process_image(media_input)

        assert result["processing_method"] == "pil_metadata_only"
        assert result["confidence"] == 0.7


class TestImagePipelineAsync:
    """End-to-end async processing tests."""

    @pytest.mark.asyncio
    async def test_process_impl_pil_only(self):
        try:
            import PIL  # noqa: F401
        except ImportError:
            pytest.skip("Pillow not installed")

        pipe = ImagePipeline()
        img_bytes = _make_minimal_jpeg()
        media_input = _make_input(img_bytes)

        with patch("media.image.pipeline._VISION_PROCESSOR_AVAILABLE", False), patch(
            "media.image.pipeline._vision_processor", None
        ):
            result = await pipe._process_impl(media_input)

        assert result.success is True
        assert result.result_data["type"] == "image_analysis"
