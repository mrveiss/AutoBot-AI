# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Voice Processor Module

GPU-accelerated audio processing with Whisper and Wav2Vec2 models.

Part of Issue #381 - God Class Refactoring
"""

import logging
import time
from typing import Any, Dict, Tuple

import numpy as np
import torch

from src.config import get_config_section

from ..base import BaseModalProcessor
from ..models import MultiModalInput, ProcessingResult
from ..types import (
    CLOSE_COMMAND_WORDS,
    INTERACTION_COMMAND_WORDS,
    LAUNCH_COMMAND_WORDS,
    MEDIA_CONTROL_COMMAND_WORDS,
    ModalityType,
    NAVIGATION_COMMAND_WORDS,
    QUERY_COMMAND_WORDS,
    SEARCH_COMMAND_WORDS,
    TEXT_INPUT_COMMAND_WORDS,
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

logger = logging.getLogger(__name__)


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
        self.logger.info("VoiceProcessor initialized with device: %s", self.device)

        # Initialize audio models if available
        self.whisper_model = None
        self.whisper_processor = None
        self.wav2vec_model = None
        self.wav2vec_processor = None

        if AUDIO_MODELS_AVAILABLE and self.enabled:
            self._load_models()

    def _load_models(self):
        """Load Whisper and Wav2Vec2 models for audio processing."""
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
            self.logger.error("Failed to load audio models: %s", e)
            # Issue #466: Will raise error on process() - no placeholder fallback
            self.logger.warning("VoiceProcessor will raise errors when processing - models unavailable")

    def __del__(self):
        """Clean up GPU resources when processor is destroyed"""
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                self.logger.info("GPU cache cleared")
        except Exception as e:
            self.logger.debug("GPU cleanup skipped: %s", e)

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
            self.logger.error("Voice processing failed: %s", e)

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

    def _prepare_audio_data(self, input_data: MultiModalInput) -> Tuple[np.ndarray, int]:
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
    ) -> Tuple[Any, str]:
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
        # Issue #466: Raise error instead of returning placeholder data
        if (
            not AUDIO_MODELS_AVAILABLE
            or self.whisper_model is None
            or self.wav2vec_model is None
        ):
            self.logger.error("Audio models not available - cannot process voice")
            raise RuntimeError(
                "Voice processing unavailable: Required models (Whisper, Wav2Vec2) are not loaded. "
                "Ensure audio models are installed and GPU/NPU resources are available."
            )

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
            self.logger.error("Error during GPU-accelerated audio processing: %s", e)
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
