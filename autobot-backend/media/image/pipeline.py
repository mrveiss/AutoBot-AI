# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Image Processing Pipeline
# Issue #735: Organize media processing into dedicated pipelines
# Issue #932: Implement actual image processing

"""Image processing pipeline for visual content."""

import asyncio
import base64
import io
import logging
from typing import Any, Dict, Optional

from media.core.pipeline import BasePipeline
from media.core.types import MediaInput, MediaType, ProcessingResult

# PIL for basic image processing (always available)
try:
    from PIL import ExifTags, Image

    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

# Optional: existing VisionProcessor for AI-powered analysis
try:
    from multimodal_processor.processors.vision import (
        VISION_MODELS_AVAILABLE,
        VisionProcessor,
    )

    _VISION_PROCESSOR_AVAILABLE = VISION_MODELS_AVAILABLE
except ImportError:
    _VISION_PROCESSOR_AVAILABLE = False
    VisionProcessor = None  # type: ignore

logger = logging.getLogger(__name__)

# Lazy singleton for VisionProcessor (loads GPU models on first use)
_vision_processor: Optional[Any] = None


def _get_vision_processor() -> Optional[Any]:
    """Lazy-load VisionProcessor; returns None if unavailable."""
    global _vision_processor
    if not _VISION_PROCESSOR_AVAILABLE:
        return None
    if _vision_processor is None and VisionProcessor is not None:
        try:
            _vision_processor = VisionProcessor()
        except Exception as exc:
            logger.warning("Failed to initialize VisionProcessor: %s", exc)
    return _vision_processor


class ImagePipeline(BasePipeline):
    """Pipeline for processing image content."""

    def __init__(self):
        """Initialize image processing pipeline."""
        super().__init__(
            pipeline_name="image",
            supported_types=[MediaType.IMAGE],
        )

    async def _process_impl(self, media_input: MediaInput) -> ProcessingResult:
        """Process image content."""
        result_data = await self._process_image(media_input)
        confidence = self._calculate_confidence(result_data)

        return ProcessingResult(
            result_id=f"image_{media_input.media_id}",
            media_id=media_input.media_id,
            media_type=media_input.media_type,
            intent=media_input.intent,
            success=True,
            confidence=confidence,
            result_data=result_data,
            processing_time=0.0,  # Set by BasePipeline
        )

    async def _process_image(self, media_input: MediaInput) -> Dict[str, Any]:
        """Load image with PIL, optionally run AI analysis via VisionProcessor."""
        if not _PIL_AVAILABLE:
            return self._unavailable_result(
                "PIL not installed. Run: pip install Pillow",
                media_input.metadata,
            )

        pil_image = await self._load_pil_image(media_input.data)
        basic_meta = self._extract_basic_metadata(pil_image)

        # Try AI-powered analysis if VisionProcessor is available
        vp = _get_vision_processor()
        if vp is not None:
            return await self._run_vision_analysis(
                pil_image, basic_meta, media_input, vp
            )

        return {
            "type": "image_analysis",
            "elements_detected": [],
            "text_detected": "",
            "confidence": 0.7,
            "processing_method": "pil_metadata_only",
            **basic_meta,
            "metadata": media_input.metadata,
        }

    async def _load_pil_image(self, data: Any) -> Any:
        """Load PIL Image from bytes, base64 string, or file path."""
        raw_bytes = await asyncio.to_thread(self._decode_input, data)
        return await asyncio.to_thread(
            lambda b: Image.open(io.BytesIO(b)).convert("RGB"), raw_bytes
        )

    def _decode_input(self, data: Any) -> bytes:
        """Normalize input data to bytes."""
        if isinstance(data, bytes):
            return data
        if hasattr(data, "convert"):  # already a PIL Image
            buf = io.BytesIO()
            data.save(buf, format="PNG")
            return buf.getvalue()
        if isinstance(data, str):
            try:
                return base64.b64decode(data)
            except Exception:
                with open(data, "rb") as fh:
                    return fh.read()
        raise ValueError(f"Unsupported image data type: {type(data)}")

    def _extract_basic_metadata(self, img: Any) -> Dict[str, Any]:
        """Extract size, format, mode, and EXIF from a PIL Image."""
        meta: Dict[str, Any] = {
            "width": img.width,
            "height": img.height,
            "mode": img.mode,
            "format": getattr(img, "format", None),
        }
        try:
            exif_raw = img._getexif()  # type: ignore[attr-defined]
            if exif_raw:
                exif = {
                    ExifTags.TAGS.get(k, k): str(v)
                    for k, v in exif_raw.items()
                    if k in ExifTags.TAGS
                }
                meta["exif"] = {
                    k: exif[k]
                    for k in ["Make", "Model", "DateTime", "GPSInfo"]
                    if k in exif
                }
        except Exception:
            pass
        return meta

    async def _run_vision_analysis(
        self,
        pil_image: Any,
        basic_meta: Dict,
        media_input: MediaInput,
        vp: Any,
    ) -> Dict[str, Any]:
        """Delegate to VisionProcessor for AI-powered image analysis."""
        from multimodal_processor.models import MultiModalInput
        from multimodal_processor.types import ModalityType, ProcessingIntent

        mm_input = MultiModalInput(
            input_id=media_input.media_id,
            modality_type=ModalityType.IMAGE,
            data=pil_image,
            intent=ProcessingIntent.ANALYSIS,
        )
        try:
            vp_result = await vp.process(mm_input)
            ai_data = vp_result.result_data or {}
            return {
                "type": "image_analysis",
                "processing_method": "vision_processor",
                "elements_detected": ai_data.get("elements_detected", []),
                "text_detected": ai_data.get("text_detected", ""),
                "caption": ai_data.get("caption", ""),
                "confidence": vp_result.confidence,
                **basic_meta,
                "metadata": media_input.metadata,
            }
        except Exception as exc:
            logger.warning("VisionProcessor failed, using PIL fallback: %s", exc)
            return {
                "type": "image_analysis",
                "elements_detected": [],
                "text_detected": "",
                "confidence": 0.7,
                "processing_method": "pil_metadata_only",
                **basic_meta,
                "metadata": media_input.metadata,
            }

    def _unavailable_result(self, reason: str, metadata: Dict) -> Dict[str, Any]:
        """Return structured result when PIL is unavailable."""
        return {
            "type": "image_analysis",
            "elements_detected": [],
            "text_detected": "",
            "processing_status": "unavailable",
            "unavailability_reason": reason,
            "confidence": 0.0,
            "metadata": metadata,
        }

    def _calculate_confidence(self, result_data: Dict[str, Any]) -> float:
        """Calculate confidence score from result data."""
        return result_data.get("confidence", 0.5)
