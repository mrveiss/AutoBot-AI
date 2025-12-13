# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unified Multi-Modal AI Processor for AutoBot
Consolidates vision, voice, and context processing with consistent interfaces
"""

import asyncio
import io
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import numpy as np
import torch
from PIL import Image

from src.enhanced_memory_manager_async import (
    TaskPriority,
    get_async_enhanced_memory_manager,
)
from src.unified_config_manager import get_config_section
from src.utils.multimodal_performance_monitor import performance_monitor

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
    logger = logging.getLogger(__name__)
    logger.warning(
        "Vision models not available. Install transformers with: pip install transformers"
    )

# Import models for audio processing
try:
    import librosa
    from transformers import (
        Wav2Vec2ForCTC,
        Wav2Vec2Processor,
        WhisperForConditionalGeneration,
        WhisperProcessor,
    )

    AUDIO_MODELS_AVAILABLE = True
except ImportError:
    AUDIO_MODELS_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning(
        "Audio models not available. Install with: pip install transformers librosa"
    )

# Import torch modules for attention fusion
try:
    import torch.nn as nn

    TORCH_NN_AVAILABLE = True
except ImportError:
    TORCH_NN_AVAILABLE = False

logger = logging.getLogger(__name__)

# Issue #380: Module-level tuple for embedding field names in result extraction
_EMBEDDING_FIELDS = ("clip_features", "audio_embedding", "embeddings")

# Performance optimization: O(1) lookup for command classification (Issue #326)
LAUNCH_COMMAND_WORDS = {"open", "launch", "start", "run"}
CLOSE_COMMAND_WORDS = {"close", "quit", "exit", "stop"}
SEARCH_COMMAND_WORDS = {"search", "find", "look for"}
TEXT_INPUT_COMMAND_WORDS = {"type", "write", "input"}
INTERACTION_COMMAND_WORDS = {"click", "press", "select"}
NAVIGATION_COMMAND_WORDS = {"navigate", "go to", "browse"}
MEDIA_CONTROL_COMMAND_WORDS = {"play", "pause", "volume"}
QUERY_COMMAND_WORDS = {"help", "what", "how", "explain"}


class ModalityType(Enum):
    """Types of input modalities supported"""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    COMBINED = "combined"


# Modality types for visual processing - placed after enum definition (Issue #326)
VISUAL_MODALITY_TYPES = {ModalityType.IMAGE, ModalityType.VIDEO}


class ProcessingIntent(Enum):
    """Types of processing intents"""

    SCREEN_ANALYSIS = "screen_analysis"
    VOICE_COMMAND = "voice_command"
    VISUAL_QA = "visual_qa"
    AUTOMATION_TASK = "automation_task"
    CONTENT_GENERATION = "content_generation"
    DECISION_MAKING = "decision_making"


class ConfidenceLevel(Enum):
    """Confidence levels for processing results"""

    VERY_HIGH = 0.9
    HIGH = 0.8
    MEDIUM = 0.6
    LOW = 0.4
    VERY_LOW = 0.2


@dataclass
class MultiModalInput:
    """Unified input data structure for all modalities"""

    input_id: str
    modality_type: ModalityType
    intent: ProcessingIntent
    data: Any  # Flexible data field for any input type
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class ProcessingResult:
    """Unified result structure for all processing types"""

    result_id: str
    input_id: str
    modality_type: ModalityType
    intent: ProcessingIntent
    success: bool
    confidence: float
    result_data: Any
    processing_time: float
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseModalProcessor:
    """Base class for modal-specific processors"""

    def __init__(self, processor_type: str):
        """Initialize base processor with type-specific logger and memory manager."""
        self.processor_type = processor_type
        self.logger = logging.getLogger(f"{__name__}.{processor_type}")
        self.memory_manager = get_async_enhanced_memory_manager()

    async def process(self, input_data: MultiModalInput) -> ProcessingResult:
        """Process input and return result"""
        raise NotImplementedError

    def calculate_confidence(self, processing_data: Any) -> float:
        """Calculate confidence score for processing result"""
        # Base implementation - override in subclasses
        return 0.5


class VisionProcessor(BaseModalProcessor):
    """Computer vision processing component with GPU acceleration"""

    def __init__(self):
        """Initialize vision processor with GPU device and model configuration."""
        super().__init__("vision")
        self.config = get_config_section("multimodal.vision")
        self.confidence_threshold = self.config.get("confidence_threshold", 0.7)
        self.processing_timeout = self.config.get("processing_timeout", 30)
        self.enabled = self.config.get("enabled", True)

        # Initialize GPU device
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.logger.info(f"VisionProcessor initialized with device: {self.device}")

        # Initialize vision models if available
        self.clip_model = None
        self.clip_processor = None
        self.blip_model = None
        self.blip_processor = None

        if VISION_MODELS_AVAILABLE and self.enabled:
            try:
                # Load CLIP model for image embeddings and classification
                self.logger.info("Loading CLIP model...")
                self.clip_model = CLIPModel.from_pretrained(
                    "openai/clip-vit-base-patch32"
                ).to(self.device)
                self.clip_processor = CLIPProcessor.from_pretrained(
                    "openai/clip-vit-base-patch32", use_fast=True
                )

                # Load BLIP-2 model for image captioning and VQA
                # Using smaller model for memory efficiency
                self.logger.info("Loading BLIP-2 model...")
                self.blip_processor = Blip2Processor.from_pretrained(
                    "Salesforce/blip2-opt-2.7b", use_fast=True
                )

                # Check if accelerate is available for device_map
                try:
                    pass

                    accelerate_available = True
                except ImportError:
                    accelerate_available = False
                    self.logger.warning(
                        "accelerate package not available, loading BLIP-2 without device_map"
                    )

                # Load BLIP-2 model with device_map only if accelerate is available
                if accelerate_available and torch.cuda.is_available():
                    self.blip_model = Blip2ForConditionalGeneration.from_pretrained(
                        "Salesforce/blip2-opt-2.7b",
                        torch_dtype=torch.float16,
                        device_map="auto",
                    )
                else:
                    self.blip_model = Blip2ForConditionalGeneration.from_pretrained(
                        "Salesforce/blip2-opt-2.7b",
                        torch_dtype=(
                            torch.float16
                            if torch.cuda.is_available()
                            else torch.float32
                        ),
                    ).to(self.device)

                # Set models to evaluation mode
                self.clip_model.eval()
                self.blip_model.eval()

                self.logger.info("Vision models loaded successfully")
            except Exception as e:
                self.logger.error(f"Failed to load vision models: {e}")
                self.logger.info("VisionProcessor will use placeholder implementation")

    def __del__(self):
        """Clean up GPU resources when processor is destroyed"""
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                self.logger.info("GPU cache cleared")
        except Exception as e:
            self.logger.debug(f"GPU cleanup skipped: {e}")

    async def process(self, input_data: MultiModalInput) -> ProcessingResult:
        """Process visual input (images, screenshots, video)"""
        start_time = time.time()

        try:
            if input_data.modality_type == ModalityType.IMAGE:
                result = await self._process_image(input_data)
            elif input_data.modality_type == ModalityType.VIDEO:
                result = await self._process_video(input_data)
            else:
                raise ValueError(f"Unsupported modality: {input_data.modality_type}")

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
            self.logger.error(f"Vision processing failed: {e}")

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
        if isinstance(data, bytes):
            return Image.open(io.BytesIO(data)).convert("RGB")
        elif isinstance(data, Image.Image):
            return data.convert("RGB")
        elif isinstance(data, str):
            # File path - read asynchronously (Issue #291)
            return await asyncio.to_thread(
                lambda p: Image.open(p).convert("RGB"), data
            )
        else:
            raise ValueError(f"Unsupported image data type: {type(data)}")

    def _process_clip_features(self, image: Image.Image):
        """Process CLIP features (Issue #315 - extracted method to reduce nesting)"""
        if not self.clip_model or not self.clip_processor:
            return None

        with torch.no_grad():
            if torch.cuda.is_available():
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    clip_inputs = self.clip_processor(
                        images=image, return_tensors="pt"
                    )
                    clip_inputs = {
                        k: v.to(self.device) for k, v in clip_inputs.items()
                    }
                    return self.clip_model.get_image_features(**clip_inputs)
            else:
                clip_inputs = self.clip_processor(
                    images=image, return_tensors="pt"
                )
                return self.clip_model.get_image_features(**clip_inputs)

    def _generate_caption(self, image: Image.Image) -> str:
        """Generate image caption (Issue #315 - extracted method to reduce nesting)"""
        if not self.blip_model or not self.blip_processor:
            return ""

        with torch.no_grad():
            if torch.cuda.is_available():
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    blip_inputs = self.blip_processor(
                        images=image, return_tensors="pt"
                    )
                    blip_inputs = {
                        k: v.to(self.device) if torch.is_tensor(v) else v
                        for k, v in blip_inputs.items()
                    }
                    generated_ids = self.blip_model.generate(
                        **blip_inputs,
                        max_length=50,
                        num_beams=3,
                        temperature=0.8,
                    )
                    return self.blip_processor.batch_decode(
                        generated_ids, skip_special_tokens=True
                    )[0].strip()
            else:
                blip_inputs = self.blip_processor(
                    images=image, return_tensors="pt"
                )
                generated_ids = self.blip_model.generate(
                    **blip_inputs, max_length=50, num_beams=3, temperature=0.8
                )
                return self.blip_processor.batch_decode(
                    generated_ids, skip_special_tokens=True
                )[0].strip()

    def _answer_visual_question(self, image: Image.Image, question: str) -> str:
        """Answer visual question (Issue #315 - extracted method to reduce nesting)"""
        if not self.blip_model or not self.blip_processor:
            return ""

        with torch.no_grad():
            if torch.cuda.is_available():
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    vqa_inputs = self.blip_processor(
                        images=image, text=question, return_tensors="pt"
                    )
                    vqa_inputs = {
                        k: v.to(self.device) if torch.is_tensor(v) else v
                        for k, v in vqa_inputs.items()
                    }
                    generated_ids = self.blip_model.generate(
                        **vqa_inputs, max_length=30
                    )
                    return self.blip_processor.batch_decode(
                        generated_ids, skip_special_tokens=True
                    )[0].strip()
            else:
                vqa_inputs = self.blip_processor(
                    images=image, text=question, return_tensors="pt"
                )
                generated_ids = self.blip_model.generate(
                    **vqa_inputs, max_length=30
                )
                return self.blip_processor.batch_decode(
                    generated_ids, skip_special_tokens=True
                )[0].strip()

    async def _process_image(self, input_data: MultiModalInput) -> Dict[str, Any]:
        """Process single image with GPU-accelerated CLIP and BLIP-2 models"""

        # Guard clause: Check if models are available (Issue #315 - early return)
        if (
            not VISION_MODELS_AVAILABLE
            or self.clip_model is None
            or self.blip_model is None
        ):
            self.logger.warning(
                "Vision models not available, using placeholder implementation"
            )
            return {
                "type": "image_analysis",
                "elements_detected": [],
                "text_detected": "",
                "caption": "Vision models not loaded",
                "confidence": 0.0,
                "processing_device": "cpu",
            }

        try:
            # Prepare image (Issue #315 - extracted method)
            image = await self._load_image(input_data.data)

            # Process with CLIP for embeddings (Issue #315 - extracted method)
            clip_features = self._process_clip_features(image)

            # Process with BLIP-2 for captioning (Issue #315 - extracted method)
            caption = self._generate_caption(image)

            # Visual Question Answering if a question is provided (Issue #315 - extracted method)
            vqa_answer = None
            question = None
            if "question" in input_data.metadata and input_data.metadata["question"]:
                question = input_data.metadata["question"]
                vqa_answer = self._answer_visual_question(image, question)

            # Clear GPU cache if using CUDA
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            # Prepare result
            result = {
                "type": "image_analysis",
                "caption": caption,
                "confidence": 0.95 if caption else 0.0,
                "processing_device": str(self.device),
                "image_size": image.size,
            }

            # Add CLIP features if available
            if clip_features is not None:
                result["clip_features"] = clip_features.cpu().numpy().tolist()
                result["clip_features_shape"] = list(clip_features.shape)

            # Add VQA answer if available
            if vqa_answer:
                result["vqa_answer"] = vqa_answer
                result["vqa_question"] = question

            # Add GPU memory usage if CUDA is available
            if torch.cuda.is_available():
                result["gpu_memory_used_mb"] = (
                    torch.cuda.memory_allocated() / 1024 / 1024
                )
                result["gpu_memory_cached_mb"] = (
                    torch.cuda.memory_reserved() / 1024 / 1024
                )

            return result

        except Exception as e:
            self.logger.error(f"Error during GPU-accelerated image processing: {e}")
            # Clear GPU cache on error
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            # Return error result
            return {
                "type": "image_analysis",
                "error": str(e),
                "caption": f"Processing failed: {str(e)}",
                "confidence": 0.0,
                "processing_device": str(self.device),
            }

    async def _process_video(self, input_data: MultiModalInput) -> Dict[str, Any]:
        """Process video input"""
        # Placeholder for video processing logic
        return {"type": "video_analysis", "frames_processed": 0, "confidence": 0.7}


class VoiceProcessor(BaseModalProcessor):
    """Voice processing component with GPU acceleration"""

    def __init__(self):
        """Initialize voice processor with GPU device and audio model configuration."""
        super().__init__("voice")
        self.config = get_config_section("multimodal.audio")
        self.confidence_threshold = self.config.get("confidence_threshold", 0.7)
        self.processing_timeout = self.config.get("processing_timeout", 30)
        self.enabled = self.config.get("enabled", True)

        # Initialize GPU device
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.logger.info(f"VoiceProcessor initialized with device: {self.device}")

        # Initialize audio models if available
        self.whisper_model = None
        self.whisper_processor = None
        self.wav2vec_model = None
        self.wav2vec_processor = None

        if AUDIO_MODELS_AVAILABLE and self.enabled:
            try:
                # Load Whisper model for speech recognition
                self.logger.info("Loading Whisper model...")
                self.whisper_processor = WhisperProcessor.from_pretrained(
                    "openai/whisper-base"
                )
                self.whisper_model = WhisperForConditionalGeneration.from_pretrained(
                    "openai/whisper-base",
                    torch_dtype=(
                        torch.float16 if torch.cuda.is_available() else torch.float32
                    ),
                ).to(self.device)

                # Load Wav2Vec2 model for audio embeddings and feature extraction
                self.logger.info("Loading Wav2Vec2 model...")
                self.wav2vec_processor = Wav2Vec2Processor.from_pretrained(
                    "facebook/wav2vec2-base-960h", use_fast=True
                )
                self.wav2vec_model = Wav2Vec2ForCTC.from_pretrained(
                    "facebook/wav2vec2-base-960h",
                    torch_dtype=(
                        torch.float16 if torch.cuda.is_available() else torch.float32
                    ),
                ).to(self.device)

                # Set models to evaluation mode
                self.whisper_model.eval()
                self.wav2vec_model.eval()

                self.logger.info("Audio models loaded successfully")
            except Exception as e:
                self.logger.error(f"Failed to load audio models: {e}")
                self.logger.info("VoiceProcessor will use placeholder implementation")

    def __del__(self):
        """Clean up GPU resources when processor is destroyed"""
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                self.logger.info("GPU cache cleared")
        except Exception as e:
            self.logger.debug(f"GPU cleanup skipped: {e}")

    async def process(self, input_data: MultiModalInput) -> ProcessingResult:
        """Process audio input (voice commands, speech)"""
        start_time = time.time()

        try:
            if input_data.modality_type == ModalityType.AUDIO:
                result = await self._process_audio(input_data)
            else:
                raise ValueError(f"Unsupported modality: {input_data.modality_type}")

            processing_time = time.time() - start_time
            confidence = self.calculate_confidence(result)

            return ProcessingResult(
                result_id=f"voice_{input_data.input_id}",
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
            self.logger.error(f"Voice processing failed: {e}")

            return ProcessingResult(
                result_id=f"voice_{input_data.input_id}",
                input_id=input_data.input_id,
                modality_type=input_data.modality_type,
                intent=input_data.intent,
                success=False,
                confidence=0.0,
                result_data=None,
                processing_time=processing_time,
                error_message=str(e),
            )

    def _prepare_audio_data(self, input_data: MultiModalInput) -> tuple:
        """Prepare and normalize audio data (Issue #315 - extracted method)"""
        audio_array = None
        sampling_rate = 16000  # Standard sampling rate for speech models

        if isinstance(input_data.data, bytes):
            audio_array = np.frombuffer(input_data.data, dtype=np.float32)
        elif isinstance(input_data.data, str):
            audio_array, sampling_rate = librosa.load(input_data.data, sr=16000)
        elif isinstance(input_data.data, np.ndarray):
            audio_array = input_data.data
        else:
            raise ValueError(f"Unsupported audio data type: {type(input_data.data)}")

        # Ensure audio is mono and normalized
        if len(audio_array.shape) > 1:
            audio_array = np.mean(audio_array, axis=1)
        audio_array = audio_array.astype(np.float32)

        return audio_array, sampling_rate

    def _transcribe_with_whisper(
        self, audio_array: np.ndarray, sampling_rate: int
    ) -> str:
        """Transcribe audio with Whisper model (Issue #315 - extracted method)"""
        if not self.whisper_model or not self.whisper_processor:
            return ""

        with torch.no_grad():
            input_features = self.whisper_processor(
                audio_array, sampling_rate=sampling_rate, return_tensors="pt"
            ).input_features

            # Use CUDA with autocast if available, otherwise CPU
            use_cuda = torch.cuda.is_available()
            if use_cuda:
                input_features = input_features.to(self.device)

            with torch.autocast(
                device_type="cuda", dtype=torch.float16, enabled=use_cuda
            ):
                predicted_ids = self.whisper_model.generate(
                    input_features, max_length=448, num_beams=5, temperature=0.8
                )
                return self.whisper_processor.batch_decode(
                    predicted_ids, skip_special_tokens=True
                )[0].strip()

    def _process_wav2vec_embeddings(
        self, audio_array: np.ndarray, sampling_rate: int
    ) -> tuple:
        """Process audio with Wav2Vec2 for embeddings (Issue #315 - extracted method)"""
        if not self.wav2vec_model or not self.wav2vec_processor:
            return None, ""

        with torch.no_grad():
            wav2vec_inputs = self.wav2vec_processor(
                audio_array,
                sampling_rate=sampling_rate,
                return_tensors="pt",
                padding=True,
            )

            # Use CUDA with autocast if available
            use_cuda = torch.cuda.is_available()
            if use_cuda:
                wav2vec_inputs = {
                    k: v.to(self.device) for k, v in wav2vec_inputs.items()
                }

            with torch.autocast(
                device_type="cuda", dtype=torch.float16, enabled=use_cuda
            ):
                logits = self.wav2vec_model(**wav2vec_inputs).logits
                hidden_states = self.wav2vec_model.wav2vec2(
                    **wav2vec_inputs
                ).last_hidden_state
                audio_embedding = torch.mean(hidden_states, dim=1).cpu().numpy()
                predicted_ids = torch.argmax(logits, dim=-1)
                wav2vec_transcription = self.wav2vec_processor.batch_decode(
                    predicted_ids
                )[0]

            return audio_embedding, wav2vec_transcription

    async def _process_audio(self, input_data: MultiModalInput) -> Dict[str, Any]:
        """Process audio input with GPU-accelerated Whisper and Wav2Vec2 models"""

        # Guard clause: Check if models are available (Issue #315 - early return)
        if (
            not AUDIO_MODELS_AVAILABLE
            or self.whisper_model is None
            or self.wav2vec_model is None
        ):
            self.logger.warning(
                "Audio models not available, using placeholder implementation"
            )
            return {
                "type": "voice_command",
                "transcribed_text": "",
                "command_type": "unknown",
                "confidence": 0.0,
                "processing_device": "cpu",
            }

        try:
            # Prepare audio data (Issue #315 - extracted method)
            audio_array, sampling_rate = self._prepare_audio_data(input_data)

            # Process with Whisper for transcription (Issue #315 - extracted method)
            transcribed_text = self._transcribe_with_whisper(audio_array, sampling_rate)

            # Process with Wav2Vec2 for embeddings (Issue #315 - extracted method)
            audio_embedding, wav2vec_transcription = self._process_wav2vec_embeddings(
                audio_array, sampling_rate
            )

            # Determine command type from transcription
            command_type = self._classify_command(transcribed_text)

            # Clear GPU cache if using CUDA
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            # Prepare result
            result = {
                "type": "voice_command",
                "transcribed_text": transcribed_text,
                "wav2vec_transcription": wav2vec_transcription,
                "command_type": command_type,
                "confidence": 0.9 if transcribed_text else 0.0,
                "processing_device": str(self.device),
                "audio_duration_seconds": len(audio_array) / sampling_rate,
            }

            # Add audio embeddings if available
            if audio_embedding is not None:
                result["audio_embedding"] = audio_embedding.tolist()
                result["audio_embedding_shape"] = list(audio_embedding.shape)

            # Add GPU memory usage if CUDA is available
            if torch.cuda.is_available():
                result["gpu_memory_used_mb"] = (
                    torch.cuda.memory_allocated() / 1024 / 1024
                )
                result["gpu_memory_cached_mb"] = (
                    torch.cuda.memory_reserved() / 1024 / 1024
                )

            return result

        except Exception as e:
            self.logger.error(f"Error during GPU-accelerated audio processing: {e}")
            # Clear GPU cache on error
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            # Return error result
            return {
                "type": "voice_command",
                "error": str(e),
                "transcribed_text": f"Processing failed: {str(e)}",
                "command_type": "error",
                "confidence": 0.0,
                "processing_device": str(self.device),
            }

    def _get_command_classification_map(self) -> list:
        """Get command word sets to classification mapping (Issue #315)."""
        return [
            (LAUNCH_COMMAND_WORDS, "launch_application"),
            (CLOSE_COMMAND_WORDS, "close_application"),
            (SEARCH_COMMAND_WORDS, "search"),
            (TEXT_INPUT_COMMAND_WORDS, "text_input"),
            (INTERACTION_COMMAND_WORDS, "interaction"),
            (NAVIGATION_COMMAND_WORDS, "navigation"),
            (MEDIA_CONTROL_COMMAND_WORDS, "media_control"),
            (QUERY_COMMAND_WORDS, "query"),
        ]

    def _classify_command(self, text: str) -> str:
        """Classify the command type from transcribed text (Issue #315)."""
        if not text:
            return "unknown"

        text_lower = text.lower()

        # Rule-based classification via lookup table (Issue #315 - reduced nesting)
        for word_set, classification in self._get_command_classification_map():
            if any(word in text_lower for word in word_set):
                return classification

        return "general_command"


class ContextProcessor(BaseModalProcessor):
    """Context-aware decision processing component"""

    def __init__(self):
        """Initialize context processor with base modality type."""
        super().__init__("context")

    async def process(self, input_data: MultiModalInput) -> ProcessingResult:
        """Process context and make decisions"""
        start_time = time.time()

        try:
            result = await self._process_context(input_data)
            processing_time = time.time() - start_time
            confidence = self.calculate_confidence(result)

            return ProcessingResult(
                result_id=f"context_{input_data.input_id}",
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
            self.logger.error(f"Context processing failed: {e}")

            return ProcessingResult(
                result_id=f"context_{input_data.input_id}",
                input_id=input_data.input_id,
                modality_type=input_data.modality_type,
                intent=input_data.intent,
                success=False,
                confidence=0.0,
                result_data=None,
                processing_time=processing_time,
                error_message=str(e),
            )

    async def _process_context(self, input_data: MultiModalInput) -> Dict[str, Any]:
        """Process contextual information"""
        # Placeholder for context processing logic
        return {
            "type": "context_decision",
            "decision": "continue",
            "reasoning": "Based on current context",
            "confidence": 0.9,
        }


class UnifiedMultiModalProcessor:
    """
    Main multi-modal processor that coordinates all modal-specific processors
    """

    def __init__(self):
        """Initialize unified processor with all modal-specific processors."""
        self.vision_processor = VisionProcessor()
        self.voice_processor = VoiceProcessor()
        self.context_processor = ContextProcessor()
        self.memory_manager = get_async_enhanced_memory_manager()
        self.logger = logging.getLogger(__name__)

        # Performance monitoring integration
        self.performance_monitor = performance_monitor

        # Enable mixed precision for RTX 4070 optimization
        self.use_amp = self.performance_monitor.enable_mixed_precision(enable=True)
        self.scaler = torch.cuda.amp.GradScaler() if self.use_amp else None

        if self.use_amp:
            self.logger.info("Mixed precision (AMP) enabled for RTX 4070 optimization")

        # Processing statistics
        self.stats = {
            "total_processed": 0,
            "successful_processed": 0,
            "failed_processed": 0,
            "avg_processing_time": 0.0,
            "modality_counts": {modality.value: 0 for modality in ModalityType},
        }

        # Initialize GPU device for fusion
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self.logger.info(
            f"UnifiedMultiModalProcessor initialized with device: {self.device}"
        )
        if torch.cuda.is_available():
            self.logger.info(
                f"GPU: {torch.cuda.get_device_name(0)}, Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f}GB"
            )

        # Initialize cross-modal fusion components
        self.fusion_network = None
        self.attention_layer = None
        self._initialize_fusion_components()

    async def _route_to_processor(
        self, input_data: MultiModalInput
    ) -> ProcessingResult:
        """Route input to appropriate processor (Issue #315 - extracted method)"""
        # Use dict-based routing to reduce if-elif chain nesting
        if input_data.modality_type in VISUAL_MODALITY_TYPES:
            return await self.vision_processor.process(input_data)
        if input_data.modality_type == ModalityType.AUDIO:
            return await self.voice_processor.process(input_data)
        if input_data.modality_type == ModalityType.TEXT:
            return await self.context_processor.process(input_data)
        if input_data.modality_type == ModalityType.COMBINED:
            return await self._process_combined(input_data)
        raise ValueError(f"Unknown modality type: {input_data.modality_type}")

    def _create_error_result(
        self,
        input_data: MultiModalInput,
        processing_time: float,
        error: Exception,
        prefix: str = "unified",
    ) -> ProcessingResult:
        """Create error result for failed processing (Issue #315 - extracted method)"""
        return ProcessingResult(
            result_id=f"{prefix}_{input_data.input_id}",
            input_id=input_data.input_id,
            modality_type=input_data.modality_type,
            intent=input_data.intent,
            success=False,
            confidence=0.0,
            result_data=None,
            processing_time=processing_time,
            error_message=str(error),
        )

    async def process(self, input_data: MultiModalInput) -> ProcessingResult:
        """
        Main processing method that routes input to appropriate processor
        """
        start_time = time.time()
        self.logger.info(
            f"Processing {input_data.modality_type.value} input with intent {input_data.intent.value}"
        )

        # Auto-optimize performance if needed
        await self.performance_monitor.auto_optimize()

        try:
            # Route to appropriate processor (Issue #315 - extracted method)
            result = await self._route_to_processor(input_data)

            # Record performance metrics
            processing_time = time.time() - start_time
            self.performance_monitor.record_processing(
                modality=input_data.modality_type.value,
                processing_time=processing_time,
                items_processed=1,
            )

            # Update statistics
            self._update_stats(result)

            # Store result in memory
            await self._store_result(result)

            return result

        except Exception as e:
            processing_time = time.time() - start_time
            self.logger.error(f"Multi-modal processing failed: {e}")

            # Record failed processing
            self.performance_monitor.record_processing(
                modality=input_data.modality_type.value,
                processing_time=processing_time,
                items_processed=0,
            )

            return self._create_error_result(input_data, processing_time, e)

    async def _process_combined(self, input_data: MultiModalInput) -> ProcessingResult:
        """Process combined multi-modal input"""
        start_time = time.time()

        try:
            # Process different modalities concurrently
            tasks = []

            # Extract different modalities from combined input
            if "image" in input_data.metadata:
                image_input = MultiModalInput(
                    input_id=f"{input_data.input_id}_image",
                    modality_type=ModalityType.IMAGE,
                    intent=input_data.intent,
                    data=input_data.metadata["image"],
                )
                tasks.append(self.vision_processor.process(image_input))

            if "audio" in input_data.metadata:
                audio_input = MultiModalInput(
                    input_id=f"{input_data.input_id}_audio",
                    modality_type=ModalityType.AUDIO,
                    intent=input_data.intent,
                    data=input_data.metadata["audio"],
                )
                tasks.append(self.voice_processor.process(audio_input))

            # Process all modalities concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Combine results
            combined_result = self._combine_results(results)
            processing_time = time.time() - start_time

            return ProcessingResult(
                result_id=f"combined_{input_data.input_id}",
                input_id=input_data.input_id,
                modality_type=input_data.modality_type,
                intent=input_data.intent,
                success=True,
                confidence=combined_result.get("confidence", 0.5),
                result_data=combined_result,
                processing_time=processing_time,
            )

        except Exception as e:
            processing_time = time.time() - start_time
            return ProcessingResult(
                result_id=f"combined_{input_data.input_id}",
                input_id=input_data.input_id,
                modality_type=input_data.modality_type,
                intent=input_data.intent,
                success=False,
                confidence=0.0,
                result_data=None,
                processing_time=processing_time,
                error_message=str(e),
            )

    def _initialize_fusion_components(self):
        """Initialize cross-modal attention fusion components."""
        if not TORCH_NN_AVAILABLE:
            self.logger.warning("PyTorch NN modules not available for fusion")
            return

        try:
            # Cross-modal attention fusion network
            # Designed to handle variable number of modalities (1-3)
            self.fusion_network = nn.Sequential(
                nn.Linear(1536, 768),  # Max concatenated embeddings (3 * 512)
                nn.ReLU(),
                nn.Dropout(0.1),
                nn.LayerNorm(768),
                nn.Linear(768, 512),
                nn.ReLU(),
                nn.Dropout(0.1),
                nn.Linear(512, 512),  # Final fused embedding
            ).to(self.device)

            # Multi-head attention for modality weighting
            self.attention_layer = nn.MultiheadAttention(
                embed_dim=512, num_heads=8, dropout=0.1, batch_first=True
            ).to(self.device)

            # Set to evaluation mode
            self.fusion_network.eval()

            self.logger.info(
                f"✅ Cross-modal fusion components initialized on {self.device}"
            )
        except Exception as e:
            self.logger.error(f"Failed to initialize fusion components: {e}")

    def _extract_embedding_from_result(
        self, result: ProcessingResult
    ) -> Optional[Any]:
        """Extract embedding from a processing result (Issue #315 - extracted method)"""
        if not result.result_data:
            return None

        # Try different embedding field names
        for field_name in _EMBEDDING_FIELDS:  # Issue #380: use module constant
            if field_name in result.result_data:
                return result.result_data.get(field_name)

        return None

    def _collect_embeddings_from_results(
        self, results: List[ProcessingResult]
    ) -> tuple:
        """Collect and filter embeddings from results (Issue #315 - extracted method)"""
        embeddings = []
        modalities = []
        confidences = []
        result_data = []

        for result in results:
            # Guard clause: Skip unsuccessful or invalid results
            if not isinstance(result, ProcessingResult) or not result.success:
                continue

            # Extract embedding using helper method
            embedding = self._extract_embedding_from_result(result)
            if embedding is None:
                continue

            # Convert to tensor if needed
            if not isinstance(embedding, torch.Tensor):
                embedding = torch.tensor(embedding, dtype=torch.float32)

            # Guard clause: Skip empty embeddings
            if embedding.numel() == 0:
                continue

            # Collect valid embedding data
            embeddings.append(embedding.to(self.device))
            modalities.append(result.modality_type.value)
            confidences.append(result.confidence)
            result_data.append(result.result_data)

        return embeddings, modalities, confidences, result_data

    def _normalize_embeddings(self, embeddings: List[torch.Tensor]) -> List[torch.Tensor]:
        """Normalize embeddings to target dimension (Issue #315 - extracted method)"""
        normalized_embeddings = []
        target_dim = 512

        for emb in embeddings:
            emb_flat = emb.flatten()
            if emb_flat.shape[0] < target_dim:
                # Pad with zeros
                padded = torch.zeros(target_dim, device=self.device)
                padded[: emb_flat.shape[0]] = emb_flat
                normalized_embeddings.append(padded)
            else:
                # Truncate or use as is
                normalized_embeddings.append(emb_flat[:target_dim])

        return normalized_embeddings

    def _apply_attention_fusion(
        self, stacked_embeddings: torch.Tensor
    ) -> tuple:
        """Apply multi-head attention (Issue #315 - extracted method)"""
        use_cuda = torch.cuda.is_available()
        with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=use_cuda):
            attended_output, attention_weights = self.attention_layer(
                stacked_embeddings, stacked_embeddings, stacked_embeddings
            )
        return attended_output, attention_weights

    def _compute_fused_embedding(
        self, weighted_embeddings: torch.Tensor
    ) -> torch.Tensor:
        """Compute final fused embedding (Issue #315 - extracted method)"""
        # Prepare input for fusion network (pad to 1536 = 3 modalities * 512)
        fusion_input = torch.zeros(1536, device=self.device)
        flat_weighted = weighted_embeddings.flatten()
        fusion_input[: min(flat_weighted.shape[0], 1536)] = flat_weighted[:1536]

        # Apply fusion network with autocast if available
        use_cuda = torch.cuda.is_available()
        with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=use_cuda):
            fused_embedding = self.fusion_network(fusion_input)

        return fused_embedding

    def _combine_results(self, results: List[ProcessingResult]) -> Dict[str, Any]:
        """Combine results from multiple processors with attention-based fusion."""
        # Guard clause: Check if we have fusion components (Issue #315 - early return)
        if self.fusion_network is None or self.attention_layer is None:
            return self._simple_combination(results)

        # Extract embeddings and metadata (Issue #315 - extracted method)
        embeddings, modalities, confidences, result_data = (
            self._collect_embeddings_from_results(results)
        )

        # Guard clause: Not enough embeddings for fusion (Issue #315 - early return)
        if len(embeddings) < 2:
            return self._simple_combination(results)

        try:
            with torch.no_grad():
                # Normalize embeddings to target dimension (Issue #315 - extracted method)
                normalized_embeddings = self._normalize_embeddings(embeddings)

                # Stack embeddings for attention [num_modalities, 512]
                stacked_embeddings = torch.stack(normalized_embeddings).unsqueeze(0)

                # Apply multi-head attention (Issue #315 - extracted method)
                attended_output, attention_weights = self._apply_attention_fusion(
                    stacked_embeddings
                )

                # Confidence-weighted fusion
                confidence_weights = torch.tensor(
                    confidences, device=self.device
                ).unsqueeze(-1)
                weighted_embeddings = attended_output.squeeze(0) * confidence_weights

                # Compute final fused embedding (Issue #315 - extracted method)
                fused_embedding = self._compute_fused_embedding(weighted_embeddings)

                # Calculate fusion confidence
                fusion_confidence = torch.mean(confidence_weights).item()

                # Extract attention weights for each modality
                if attention_weights is not None:
                    attn_scores = attention_weights.mean(dim=1).squeeze().cpu().numpy()
                    modality_contributions = dict(
                        zip(modalities, attn_scores[: len(modalities)])
                    )
                else:
                    modality_contributions = {
                        m: 1.0 / len(modalities) for m in modalities
                    }

            # Clear GPU cache
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            return {
                "fusion_type": "attention_based",
                "fused_embedding": fused_embedding.cpu().numpy().tolist(),
                "fusion_confidence": fusion_confidence,
                "modality_contributions": modality_contributions,
                "modalities_fused": modalities,
                "success_count": len(embeddings),
                "total_count": len(results),
                "individual_results": result_data,
            }

        except Exception as e:
            self.logger.error(f"Attention fusion failed: {e}")
            return self._simple_combination(results)

    def _simple_combination(self, results: List[ProcessingResult]) -> Dict[str, Any]:
        """Simple fallback combination without attention fusion."""
        combined = {
            "fusion_type": "simple_average",
            "results": [],
            "confidence": 0.0,
            "success_count": 0,
            "total_count": len(results),
        }

        confidence_sum = 0.0
        for result in results:
            if isinstance(result, ProcessingResult):
                combined["results"].append(
                    {
                        "modality": result.modality_type.value,
                        "success": result.success,
                        "confidence": result.confidence,
                        "data": result.result_data,
                    }
                )
                if result.success:
                    combined["success_count"] += 1
                    confidence_sum += result.confidence

        # Calculate average confidence
        if combined["success_count"] > 0:
            combined["confidence"] = confidence_sum / combined["success_count"]

        return combined

    def _update_stats(self, result: ProcessingResult):
        """Update processing statistics"""
        self.stats["total_processed"] += 1

        if result.success:
            self.stats["successful_processed"] += 1
        else:
            self.stats["failed_processed"] += 1

        # Update modality counts
        self.stats["modality_counts"][result.modality_type.value] += 1

        # Update average processing time
        total_time = (
            self.stats["avg_processing_time"] * (self.stats["total_processed"] - 1)
            + result.processing_time
        )
        self.stats["avg_processing_time"] = total_time / self.stats["total_processed"]

    async def _store_result(self, result: ProcessingResult):
        """Store processing result in memory"""
        try:
            task_data = {
                "result_id": result.result_id,
                "modality": result.modality_type.value,
                "intent": result.intent.value,
                "success": result.success,
                "confidence": result.confidence,
                "processing_time": result.processing_time,
            }

            await self.memory_manager.store_task(
                task_id=result.result_id,
                task_type="multimodal_processing",
                description=f"Multi-modal processing: {result.modality_type.value}",
                status="completed" if result.success else "failed",
                priority=TaskPriority.MEDIUM,
                subtasks=[],
                context=task_data,
                execution_details={"result_data": result.result_data},
            )

        except Exception as e:
            self.logger.warning(f"Failed to store processing result: {e}")

    def _group_inputs_by_modality(
        self, inputs: List[MultiModalInput]
    ) -> Dict[str, List[MultiModalInput]]:
        """Group inputs by modality type (Issue #315 - extracted method)"""
        modality_groups: Dict[str, List[MultiModalInput]] = {}
        for inp in inputs:
            modality = inp.modality_type.value
            if modality not in modality_groups:
                modality_groups[modality] = []
            modality_groups[modality].append(inp)
        return modality_groups

    async def _process_single_batch(
        self, batch: List[MultiModalInput], modality: str
    ) -> List[ProcessingResult]:
        """Process a single batch of inputs (Issue #315 - extracted method)"""
        # Memory optimization before processing
        if self.performance_monitor.should_optimize():
            await self.performance_monitor.optimize_gpu_memory()

        # Route to specialized batch processor or process individually
        if modality == "image" and len(batch) > 1:
            return await self._process_image_batch(batch)
        if modality == "audio" and len(batch) > 1:
            return await self._process_audio_batch(batch)

        # Process individually for other modalities or small batches
        return [await self.process(inp) for inp in batch]

    async def _process_modality_group(
        self, modality: str, group_inputs: List[MultiModalInput]
    ) -> List[ProcessingResult]:
        """Process all batches for a single modality (Issue #315 - extracted method)"""
        results = []
        batch_size = self.performance_monitor.get_optimal_batch_size(modality)

        for i in range(0, len(group_inputs), batch_size):
            batch = group_inputs[i : i + batch_size]
            self.logger.debug(f"Processing batch of {len(batch)} {modality} inputs")
            batch_results = await self._process_single_batch(batch, modality)
            results.extend(batch_results)

        return results

    async def _fallback_individual_processing(
        self, inputs: List[MultiModalInput]
    ) -> List[ProcessingResult]:
        """Fallback to individual processing on batch failure (Issue #315 - extracted)"""
        results = []
        for inp in inputs:
            result = await self._process_input_with_fallback(inp)
            results.append(result)
        return results

    async def _process_input_with_fallback(
        self, inp: MultiModalInput
    ) -> ProcessingResult:
        """Process single input with error handling (Issue #315 - extracted method)"""
        try:
            return await self.process(inp)
        except Exception as individual_error:
            self.logger.error(
                f"Individual processing failed for {inp.input_id}: {individual_error}"
            )
            return self._create_error_result(inp, 0.0, individual_error, "batch_error")

    async def process_batch(
        self, inputs: List[MultiModalInput]
    ) -> List[ProcessingResult]:
        """
        Process multiple inputs efficiently using optimized batching
        """
        if not inputs:
            return []

        self.logger.info(f"Processing batch of {len(inputs)} inputs")
        start_time = time.time()

        # Auto-optimize performance before batch processing
        await self.performance_monitor.auto_optimize()

        try:
            # Group inputs by modality (Issue #315 - extracted method)
            modality_groups = self._group_inputs_by_modality(inputs)

            # Process each modality group (Issue #315 - extracted method)
            results = []
            for modality, group_inputs in modality_groups.items():
                group_results = await self._process_modality_group(modality, group_inputs)
                results.extend(group_results)

            # Record batch processing performance
            total_processing_time = time.time() - start_time
            self.performance_monitor.record_processing(
                modality="batch",
                processing_time=total_processing_time,
                items_processed=len(inputs),
            )

            self.logger.info(
                f"Batch processing completed: {len(results)} results in {total_processing_time:.2f}s"
            )
            return results

        except Exception as e:
            self.logger.error(f"Batch processing failed: {e}")
            return await self._fallback_individual_processing(inputs)

    async def _process_image_batch(
        self, batch: List[MultiModalInput]
    ) -> List[ProcessingResult]:
        """Process a batch of images efficiently"""
        results = []

        try:
            # Use mixed precision if available
            if self.use_amp and torch.cuda.is_available():
                with torch.cuda.amp.autocast():
                    for inp in batch:
                        result = await self.vision_processor.process(inp)
                        results.append(result)
            else:
                for inp in batch:
                    result = await self.vision_processor.process(inp)
                    results.append(result)

        except Exception as e:
            self.logger.error(f"Image batch processing failed: {e}")
            # Fallback to individual processing
            for inp in batch:
                try:
                    result = await self.vision_processor.process(inp)
                    results.append(result)
                except Exception as individual_error:
                    error_result = ProcessingResult(
                        result_id=f"image_batch_error_{inp.input_id}",
                        input_id=inp.input_id,
                        modality_type=inp.modality_type,
                        intent=inp.intent,
                        success=False,
                        confidence=0.0,
                        result_data=None,
                        processing_time=0.0,
                        error_message=str(individual_error),
                    )
                    results.append(error_result)

        return results

    async def _process_audio_batch(
        self, batch: List[MultiModalInput]
    ) -> List[ProcessingResult]:
        """Process a batch of audio inputs efficiently"""
        results = []

        try:
            # Use mixed precision if available
            if self.use_amp and torch.cuda.is_available():
                with torch.cuda.amp.autocast():
                    for inp in batch:
                        result = await self.voice_processor.process(inp)
                        results.append(result)
            else:
                for inp in batch:
                    result = await self.voice_processor.process(inp)
                    results.append(result)

        except Exception as e:
            self.logger.error(f"Audio batch processing failed: {e}")
            # Fallback to individual processing
            for inp in batch:
                try:
                    result = await self.voice_processor.process(inp)
                    results.append(result)
                except Exception as individual_error:
                    error_result = ProcessingResult(
                        result_id=f"audio_batch_error_{inp.input_id}",
                        input_id=inp.input_id,
                        modality_type=inp.modality_type,
                        intent=inp.intent,
                        success=False,
                        confidence=0.0,
                        result_data=None,
                        processing_time=0.0,
                        error_message=str(individual_error),
                    )
                    results.append(error_result)

        return results

    def get_stats(self) -> Dict[str, Any]:
        """Get processing statistics"""
        return self.stats.copy()

    def reset_stats(self):
        """Reset processing statistics"""
        self.stats = {
            "total_processed": 0,
            "successful_processed": 0,
            "failed_processed": 0,
            "avg_processing_time": 0.0,
            "modality_counts": {modality.value: 0 for modality in ModalityType},
        }


# Singleton instance for global access
unified_processor = UnifiedMultiModalProcessor()
