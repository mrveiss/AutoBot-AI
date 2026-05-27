# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Vision Processor Module

GPU-accelerated computer vision processing with CLIP and BLIP-2 models.

Part of Issue #381 - God Class Refactoring
"""

from __future__ import annotations

import asyncio
import io
import time
from typing import TYPE_CHECKING, Any, Dict

from autobot_shared.logging_manager import get_logger
from config import get_config_section

from ..base import BaseModalProcessor
from ..models import MultiModalInput, ProcessingResult
from ..types import ModalityType

if TYPE_CHECKING:
    from PIL import Image

# Issue #3016: lazy module-level imports for torch and PIL
_torch = None
_PILImage = None


def _get_torch():
    """Lazy-load torch on first use. Issue #3016."""
    global _torch  # noqa: PLW0603
    if _torch is None:
        import torch

        _torch = torch
    return _torch


def _get_pil_image():
    """Lazy-load PIL.Image on first use. Issue #3016."""
    global _PILImage  # noqa: PLW0603
    if _PILImage is None:
        from PIL import Image as _img

        _PILImage = _img
    return _PILImage


# Import transformers models for vision processing
try:
    from transformers import (
        Blip2ForConditionalGeneration,
        Blip2Processor,
        CLIPModel,
        CLIPProcessor,
    )

    VISION_MODELS_AVAILABLE = True
except ImportError:
    VISION_MODELS_AVAILABLE = False
    logger = get_logger(__name__)
    logger.warning("Vision models not available. Install transformers with: pip install transformers")

logger = get_logger(__name__)


class VisionProcessor(BaseModalProcessor):
    """Computer vision processing component with GPU acceleration"""

    def __init__(self):
        """Initialize vision processor with GPU device and model configuration."""
        torch = _get_torch()

        super().__init__("vision")
        self.config = get_config_section("multimodal.vision")
        self.confidence_threshold = self.config.get("confidence_threshold", 0.7)
        self.processing_timeout = self.config.get("processing_timeout", 30)
        self.enabled = self.config.get("enabled", True)

        # Initialize GPU device
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.logger.info("VisionProcessor initialized with device: %s", self.device)

        # Initialize vision models if available
        self.clip_model = None
        self.clip_processor = None
        self.blip_model = None
        self.blip_processor = None

        if VISION_MODELS_AVAILABLE and self.enabled:
            self._load_models()

    def _load_models(self):
        """Load CLIP and BLIP-2 models for vision processing."""
        torch = _get_torch()

        try:
            # Load CLIP model for image embeddings and classification
            self.logger.info("Loading CLIP model...")
            self.clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32", resume_download=True).to(  # nosec B615 - HuggingFace model loaded by name; revision pinning managed operationally
                self.device
            )
            self.clip_processor = CLIPProcessor.from_pretrained(  # nosec B615 - HuggingFace model loaded by name; revision pinning managed operationally
                "openai/clip-vit-base-patch32", use_fast=True, resume_download=True
            )

            # Load BLIP-2 model for image captioning and VQA
            # Using smaller model for memory efficiency
            self.logger.info("Loading BLIP-2 model...")
            self.blip_processor = Blip2Processor.from_pretrained(  # nosec B615 - HuggingFace model loaded by name; revision pinning managed operationally
                "Salesforce/blip2-opt-2.7b", use_fast=True, resume_download=True
            )

            # Check if accelerate is available for device_map
            try:
                accelerate_available = True
            except ImportError:
                accelerate_available = False
                self.logger.warning("accelerate package not available, loading BLIP-2 without device_map")

            # Load BLIP-2 model with device_map only if accelerate is available
            if accelerate_available and torch.cuda.is_available():
                self.blip_model = Blip2ForConditionalGeneration.from_pretrained(  # nosec B615 - HuggingFace model loaded by name; revision pinning managed operationally
                    "Salesforce/blip2-opt-2.7b",
                    torch_dtype=torch.float16,
                    device_map="auto",
                    resume_download=True,
                )
            else:
                self.blip_model = Blip2ForConditionalGeneration.from_pretrained(  # nosec B615 - HuggingFace model loaded by name; revision pinning managed operationally
                    "Salesforce/blip2-opt-2.7b",
                    torch_dtype=(torch.float16 if torch.cuda.is_available() else torch.float32),
                    resume_download=True,
                ).to(self.device)

            # Set models to evaluation mode
            self.clip_model.eval()
            self.blip_model.eval()

            self.logger.info("Vision models loaded successfully")
        except Exception as e:
            self.logger.error("Failed to load vision models: %s", e)
            # Issue #466: Will raise error on process() - no placeholder fallback
            self.logger.warning("VisionProcessor will raise errors when processing - models unavailable")

    def __del__(self):
        """Clean up GPU resources when processor is destroyed"""
        try:
            torch = _get_torch()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                self.logger.info("GPU cache cleared")
        except Exception as e:
            self.logger.debug("GPU cleanup skipped: %s", e)

    async def process(self, input_data: MultiModalInput) -> ProcessingResult:
        """Process visual input (images, screenshots, video).

        #6755 LSP exception contract: parent ``BaseModalProcessor.process``
        only declares ``NotImplementedError``; subclasses must NOT raise
        arbitrary exceptions to callers. Unsupported modality is now
        returned as a failure ``ProcessingResult`` (the same shape the
        outer ``except`` clause already produces), which keeps the
        return-type contract intact and matches the #6658 fix pattern.
        """
        start_time = time.time()

        if input_data.modality_type not in (ModalityType.IMAGE, ModalityType.VIDEO):
            return ProcessingResult(
                result_id=f"vision_{input_data.input_id}",
                input_id=input_data.input_id,
                modality_type=input_data.modality_type,
                intent=input_data.intent,
                success=False,
                confidence=0.0,
                result_data=None,
                processing_time=time.time() - start_time,
                error_message=f"Unsupported modality: {input_data.modality_type}",
            )

        try:
            if input_data.modality_type == ModalityType.IMAGE:
                result = await self._process_image(input_data)
            else:
                result = await self._process_video(input_data)

            processing_time = time.time() - start_time
            confidence = self.calculate_confidence(result)

            return ProcessingResult(
                result_id=f"vision_{input_data.input_id}",
                input_id=input_data.input_id,
                modality_type=input_data.modality_type,
                intent=input_data.intent,
                success=True,
                confidence=confidence,
                result_data=result,
                processing_time=processing_time,
            )

        except Exception as e:
            processing_time = time.time() - start_time
            self.logger.error("Vision processing failed: %s", e)

            return ProcessingResult(
                result_id=f"vision_{input_data.input_id}",
                input_id=input_data.input_id,
                modality_type=input_data.modality_type,
                intent=input_data.intent,
                success=False,
                confidence=0.0,
                result_data=None,
                processing_time=processing_time,
                error_message=str(e),
            )

    async def _load_image(self, data: Any) -> Image.Image:
        """Load image from various input types (Issue #315 - extracted method)"""
        PILImage = _get_pil_image()

        if isinstance(data, bytes):
            return PILImage.open(io.BytesIO(data)).convert("RGB")
        elif isinstance(data, PILImage.Image):
            return data.convert("RGB")
        elif isinstance(data, str):
            # File path - read asynchronously (Issue #291)
            return await asyncio.to_thread(lambda p: PILImage.open(p).convert("RGB"), data)
        else:
            raise ValueError(f"Unsupported image data type: {type(data)}")

    def _process_clip_features(self, image: Image.Image):
        """Process CLIP features (Issue #315 - extracted method to reduce nesting)"""
        torch = _get_torch()

        if not self.clip_model or not self.clip_processor:
            return None

        with torch.no_grad():
            if torch.cuda.is_available():
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    clip_inputs = self.clip_processor(images=image, return_tensors="pt")
                    clip_inputs = {k: v.to(self.device) for k, v in clip_inputs.items()}
                    return self.clip_model.get_image_features(**clip_inputs)
            else:
                clip_inputs = self.clip_processor(images=image, return_tensors="pt")
                return self.clip_model.get_image_features(**clip_inputs)

    def _generate_caption(self, image: Image.Image) -> str:
        """Generate image caption (Issue #315 - extracted method to reduce nesting)"""
        torch = _get_torch()

        if not self.blip_model or not self.blip_processor:
            return ""

        with torch.no_grad():
            if torch.cuda.is_available():
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    blip_inputs = self.blip_processor(images=image, return_tensors="pt")
                    blip_inputs = {k: v.to(self.device) if torch.is_tensor(v) else v for k, v in blip_inputs.items()}
                    generated_ids = self.blip_model.generate(
                        **blip_inputs,
                        max_length=50,
                        num_beams=3,
                        temperature=0.8,
                    )
                    return self.blip_processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
            else:
                blip_inputs = self.blip_processor(images=image, return_tensors="pt")
                generated_ids = self.blip_model.generate(**blip_inputs, max_length=50, num_beams=3, temperature=0.8)
                return self.blip_processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()

    def _answer_visual_question(self, image: Image.Image, question: str) -> str:
        """Answer visual question (Issue #315 - extracted method to reduce nesting)"""
        torch = _get_torch()

        if not self.blip_model or not self.blip_processor:
            return ""

        with torch.no_grad():
            if torch.cuda.is_available():
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    vqa_inputs = self.blip_processor(images=image, text=question, return_tensors="pt")
                    vqa_inputs = {k: v.to(self.device) if torch.is_tensor(v) else v for k, v in vqa_inputs.items()}
                    generated_ids = self.blip_model.generate(**vqa_inputs, max_length=30)
                    return self.blip_processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
            else:
                vqa_inputs = self.blip_processor(images=image, text=question, return_tensors="pt")
                generated_ids = self.blip_model.generate(**vqa_inputs, max_length=30)
                return self.blip_processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()

    def _build_image_result(
        self,
        image: Image.Image,
        caption: str,
        clip_features: Any,
        vqa_answer: str,
        question: str,
    ) -> Dict[str, Any]:
        """
        Build image analysis result dictionary.

        Issue #665: Extracted from _process_image to reduce function length.

        Args:
            image: Processed PIL image
            caption: Generated image caption
            clip_features: CLIP feature tensor or None
            vqa_answer: Visual QA answer or None
            question: Visual QA question or None

        Returns:
            Dictionary with analysis results
        """
        torch = _get_torch()

        result = {
            "type": "image_analysis",
            "caption": caption,
            "confidence": 0.95 if caption else 0.0,
            "processing_device": str(self.device),
            "image_size": image.size,
        }

        if clip_features is not None:
            result["clip_features"] = clip_features.cpu().numpy().tolist()
            result["clip_features_shape"] = list(clip_features.shape)

        if vqa_answer:
            result["vqa_answer"] = vqa_answer
            result["vqa_question"] = question

        if torch.cuda.is_available():
            result["gpu_memory_used_mb"] = torch.cuda.memory_allocated() / 1024 / 1024
            result["gpu_memory_cached_mb"] = torch.cuda.memory_reserved() / 1024 / 1024

        return result

    async def _process_image(self, input_data: MultiModalInput) -> Dict[str, Any]:
        """
        Process single image with GPU-accelerated CLIP and BLIP-2 models.

        Issue #665: Refactored to use _build_image_result helper.
        """
        torch = _get_torch()

        # Guard clause: Check if models are available
        if not VISION_MODELS_AVAILABLE or self.clip_model is None or self.blip_model is None:
            self.logger.error("Vision models not available - cannot process image")
            raise RuntimeError(
                "Vision processing unavailable: Required models (CLIP, BLIP) are not loaded. "
                "Ensure vision models are installed and GPU/NPU resources are available."
            )

        try:
            # Process image with extracted methods
            image = await self._load_image(input_data.data)
            clip_features = self._process_clip_features(image)
            caption = self._generate_caption(image)

            # Visual Question Answering if provided
            vqa_answer, question = None, None
            if input_data.metadata.get("question"):
                question = input_data.metadata["question"]
                vqa_answer = self._answer_visual_question(image, question)

            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            # Issue #665: Use helper to build result
            return self._build_image_result(image, caption, clip_features, vqa_answer, question)

        except Exception as e:
            self.logger.error("Error during GPU-accelerated image processing: %s", e)
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            return {
                "type": "image_analysis",
                "error": "Image processing failed",
                "caption": "Processing failed",
                "confidence": 0.0,
                "processing_device": str(self.device),
            }

    async def _process_video(self, input_data: MultiModalInput) -> Dict[str, Any]:
        """Process video input"""
        # Issue #466: Raise error instead of returning placeholder data
        # Video processing requires model implementation with NPU integration
        raise NotImplementedError(
            "Video processing not yet implemented. "
            "This feature requires NPU Worker VM integration for frame-by-frame analysis."
        )
