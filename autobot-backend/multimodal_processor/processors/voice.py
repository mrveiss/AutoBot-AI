# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Voice Processor Module

GPU-accelerated audio processing with Whisper and Wav2Vec2 models.

Part of Issue #381 - God Class Refactoring
"""

import asyncio
import dataclasses
import time
from typing import Any, Dict, Tuple

import numpy as np

from autobot_shared.audio_params import STT_SAMPLE_RATE
from autobot_shared.env_utils import env_float, env_int
from autobot_shared.logging_manager import get_logger
from config import get_config_section
from llm_shared.torch_loader import lazy_torch
from media.audio.decode import decode_audio_bytes, decode_audio_bytes_async
from media.audio.pipeline import get_whisper_pipeline, transcribe_array, whisper_device, whisper_loadable
from voice_processing.hallucination_filter import is_silence_hallucination, peak_window_rms

from ..base import BaseModalProcessor
from ..models import MultiModalInput, MultimodalResult
from ..types import (
    CLOSE_COMMAND_WORDS,
    INTERACTION_COMMAND_WORDS,
    LAUNCH_COMMAND_WORDS,
    MEDIA_CONTROL_COMMAND_WORDS,
    NAVIGATION_COMMAND_WORDS,
    QUERY_COMMAND_WORDS,
    SEARCH_COMMAND_WORDS,
    TEXT_INPUT_COMMAND_WORDS,
    ModalityType,
)

# Issue #3016: lazy module-level import for torch
# Issue #12714: torch loader unified onto the shared thread-safe llm_shared.torch_loader.


def _get_torch():
    """Lazy-load torch on first use. Issue #3016."""
    return lazy_torch()


# Import models for audio processing
try:
    import librosa
    from transformers import (
        Wav2Vec2ForCTC,
        Wav2Vec2Processor,
    )

    AUDIO_MODELS_AVAILABLE = True
except ImportError:
    AUDIO_MODELS_AVAILABLE = False
    logger = get_logger(__name__)
    logger.warning("Audio models not available. Install with: pip install transformers librosa")

logger = get_logger(__name__)


# Issue #13207: fallbacks for the multimodal.voice section, env-overridable.
#
# These match the values VoiceProcessor was *actually* running on before the
# key was corrected, and defaults.py was aligned to them in the same change so
# fixing the lookup could not move a threshold as a side effect. The section
# previously declared 0.8 / 15, but those numbers were unreachable for the
# whole life of the code and were never validated against real audio; the
# integration suite also configures multimodal.voice.confidence_threshold=0.7.
# Retuning voice confidence/timeout is a deliberate change with its own
# evidence, not a rider on a typo fix.
VOICE_CONFIDENCE_THRESHOLD_DEFAULT = env_float("AUTOBOT_MULTIMODAL_VOICE_CONFIDENCE_THRESHOLD", 0.7)
VOICE_PROCESSING_TIMEOUT_DEFAULT = env_int("AUTOBOT_MULTIMODAL_VOICE_PROCESSING_TIMEOUT", 30)

#: Decode settings this processor has always used, kept identical when Whisper moved
#: onto the one pinned pipeline (#17778) so transcripts do not change.
WHISPER_GENERATE_KWARGS = {"max_length": 448, "num_beams": 5, "temperature": 0.8}


class VoiceProcessor(BaseModalProcessor):
    """Voice processing component with GPU acceleration"""

    def __init__(self):
        """Initialize voice processor with GPU device and audio model configuration."""
        torch = _get_torch()

        super().__init__("voice")
        # Issue #13207: this read "multimodal.audio", a section that has never
        # existed under any path, so get_config_section always returned {} and
        # every value below silently came from the literal fallbacks. The live
        # casualty was `enabled`, which gates model loading below.
        self.config = get_config_section("multimodal.voice")
        self.confidence_threshold = self.config.get("confidence_threshold", VOICE_CONFIDENCE_THRESHOLD_DEFAULT)
        self.processing_timeout = self.config.get("processing_timeout", VOICE_PROCESSING_TIMEOUT_DEFAULT)
        self.enabled = self.config.get("enabled", True)

        # Initialize GPU device
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.logger.info("VoiceProcessor initialized with device: %s", self.device)

        # Initialize audio models if available
        self.wav2vec_model = None
        self.wav2vec_processor = None

        if AUDIO_MODELS_AVAILABLE and self.enabled:
            self._load_models()

    def _load_models(self):
        """Load the Wav2Vec2 model for audio embeddings and command classification.

        #13034: pinned to an exact, integrity-verified revision instead of the
        mutable default branch -- see autobot_shared/pinned_model_registry.py.
        Whisper is no longer loaded here (#17778): transcription goes through the
        one pinned pipeline, ``media.audio.pipeline.get_whisper_pipeline``.
        """
        from autobot_shared.pinned_model_registry import get_pinned_revision, verify_cached_model

        torch = _get_torch()
        wav2vec_repo_id = "facebook/wav2vec2-base-960h"
        wav2vec_revision = get_pinned_revision(wav2vec_repo_id)

        from autobot_shared.pinned_model_registry import ModelIntegrityError

        try:
            # #17124: load into locals and verify BEFORE assigning to self.* (fail-open otherwise).
            self.logger.info("Loading Wav2Vec2 model...")
            wav2vec_processor = Wav2Vec2Processor.from_pretrained(
                wav2vec_repo_id, revision=wav2vec_revision, use_fast=True
            )
            wav2vec_model = Wav2Vec2ForCTC.from_pretrained(
                wav2vec_repo_id,
                revision=wav2vec_revision,
                torch_dtype=(torch.float16 if torch.cuda.is_available() else torch.float32),
            ).to(self.device)
            verify_cached_model(wav2vec_repo_id)
            wav2vec_model.eval()
            self.wav2vec_processor = wav2vec_processor
            self.wav2vec_model = wav2vec_model

            self.logger.info("Wav2Vec2 model loaded successfully")
        except ModelIntegrityError as e:
            # #17124: named, distinct from a generic load failure -- a tampered
            # cached model was detected. The model's verify raised before its
            # self.* attributes were assigned.
            self.logger.error("SECURITY: audio model integrity check failed, refusing to serve: %s", e)
            self.logger.warning("VoiceProcessor will raise errors when processing - models unavailable")
        except Exception as e:
            self.logger.error("Failed to load audio models: %s", e)
            # Issue #466: Will raise error on process() - no placeholder fallback
            self.logger.warning("VoiceProcessor will raise errors when processing - models unavailable")

    def __del__(self):
        """Clean up GPU resources when processor is destroyed"""
        try:
            torch = _get_torch()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                self.logger.info("GPU cache cleared")
        except Exception as e:
            self.logger.debug("GPU cleanup skipped: %s", e)

    def _failure_result(
        self,
        input_data: MultiModalInput,
        processing_time: float,
        message: str,
    ) -> MultimodalResult:
        """Build a failed MultimodalResult with a stated reason. Issue #13207."""
        return MultimodalResult(
            result_id=f"voice_{input_data.input_id}",
            input_id=input_data.input_id,
            modality_type=input_data.modality_type,
            intent=input_data.intent,
            success=False,
            confidence=0.0,
            result_data=None,
            processing_time=processing_time,
            error_message=message,
        )

    def _threshold_checked_result(
        self,
        input_data: MultiModalInput,
        result: Dict[str, Any],
        processing_time: float,
    ) -> MultimodalResult:
        """Apply the configured confidence threshold to a completed result.

        Issue #13207: confidence_threshold was read from config and then never
        consulted. A result under it is reported as a failure with a stated
        reason rather than passed off as a successful command.
        """
        confidence = self.calculate_confidence(result)
        below = confidence < self.confidence_threshold
        if below:
            self.logger.info(
                "Voice result confidence %.2f below threshold %.2f — not treated as a command",
                confidence,
                self.confidence_threshold,
            )
        return MultimodalResult(
            result_id=f"voice_{input_data.input_id}",
            input_id=input_data.input_id,
            modality_type=input_data.modality_type,
            intent=input_data.intent,
            success=not below,
            confidence=confidence,
            result_data=result,
            processing_time=processing_time,
            error_message=(
                f"Voice confidence {confidence:.2f} below configured threshold {self.confidence_threshold:.2f}"
                if below
                else None
            ),
        )

    async def process(self, input_data: MultiModalInput) -> MultimodalResult:
        """Process audio input (voice commands, speech)"""
        start_time = time.time()

        if not self.enabled:
            # Issue #13207 review E: without this, a deliberately disabled voice
            # processor reports "models are not loaded, check your GPU/NPU",
            # sending an operator to debug hardware they never broke.
            return self._build_disabled_result(input_data, time.time() - start_time)

        if input_data.modality_type != ModalityType.AUDIO:
            # #6755 LSP exception contract: don't raise — parent
            # `BaseModalProcessor.process` only declares NotImplementedError;
            # subclasses must return a failure MultimodalResult, not propagate
            # ValueError. Same fix pattern as #6658 / VisionProcessor.
            return self._failure_result(
                input_data,
                time.time() - start_time,
                f"Unsupported modality: {input_data.modality_type}",
            )

        try:
            result = await asyncio.wait_for(
                self._process_audio(input_data),
                timeout=self.processing_timeout,
            )
            return self._threshold_checked_result(input_data, result, time.time() - start_time)

        except asyncio.TimeoutError:
            self.logger.error("Voice processing exceeded %ss timeout", self.processing_timeout)
            return self._failure_result(
                input_data,
                time.time() - start_time,
                f"Voice processing exceeded the configured {self.processing_timeout}s timeout",
            )

        except Exception as e:
            self.logger.error("Voice processing failed: %s", e)
            return self._failure_result(input_data, time.time() - start_time, str(e))

    def calculate_confidence(self, processing_data: Any) -> float:
        """Return the confidence the audio pipeline actually reported. Issue #13207.

        The base implementation returns a flat 0.5 for every result, which made
        MultimodalResult.confidence meaningless and left confidence_threshold
        with nothing to compare against.
        """
        if isinstance(processing_data, dict):
            return float(processing_data.get("confidence", 0.0))
        return 0.0

    def _build_disabled_result(self, input_data: MultiModalInput, processing_time: float) -> MultimodalResult:
        """Report that voice is switched off, not that the hardware is broken."""
        self.logger.info("Voice processing requested while multimodal.voice.enabled is false")
        return self._failure_result(
            input_data,
            processing_time,
            "Voice processing is disabled by configuration (multimodal.voice.enabled=false)",
        )

    def _prepare_audio_data(self, input_data: MultiModalInput) -> Tuple[np.ndarray, int]:
        """Prepare and normalize audio data (Issue #315 - extracted method)"""
        audio_array = None
        sampling_rate = STT_SAMPLE_RATE  # Standard sampling rate for speech models

        if isinstance(input_data.data, bytes):
            # #17778: these are a FILE's bytes (WAV/webm from the upload route),
            # not raw samples; reinterpreting them as float32 transcribed noise.
            audio_array = decode_audio_bytes(input_data.data)
        elif isinstance(input_data.data, str):
            audio_array, sampling_rate = librosa.load(input_data.data, sr=STT_SAMPLE_RATE)
        elif isinstance(input_data.data, np.ndarray):
            audio_array = input_data.data
        else:
            raise ValueError(f"Unsupported audio data type: {type(input_data.data)}")

        # Ensure audio is mono and normalized
        if len(audio_array.shape) > 1:
            audio_array = np.mean(audio_array, axis=1)
        audio_array = audio_array.astype(np.float32)

        return audio_array, sampling_rate

    def _transcribe_with_whisper(self, audio_array: np.ndarray, sampling_rate: int) -> str:
        """Transcribe via the ONE pinned Whisper pipeline (#17778), same decode settings.

        BLOCKING (first use loads the model): ``_process_audio`` runs it in a thread.
        """
        pipe = get_whisper_pipeline()
        if pipe is None:
            raise RuntimeError("Voice processing unavailable: the Whisper pipeline could not be loaded.")
        return transcribe_array(pipe, audio_array, sampling_rate, generate_kwargs=WHISPER_GENERATE_KWARGS).text

    def _process_wav2vec_embeddings(self, audio_array: np.ndarray, sampling_rate: int) -> Tuple[Any, str]:
        """Process audio with Wav2Vec2 for embeddings (Issue #315 - extracted method)"""
        torch = _get_torch()

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
                wav2vec_inputs = {k: v.to(self.device) for k, v in wav2vec_inputs.items()}

            with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=use_cuda):
                logits = self.wav2vec_model(**wav2vec_inputs).logits
                hidden_states = self.wav2vec_model.wav2vec2(**wav2vec_inputs).last_hidden_state
                audio_embedding = torch.mean(hidden_states, dim=1).cpu().numpy()
                predicted_ids = torch.argmax(logits, dim=-1)
                wav2vec_transcription = self.wav2vec_processor.batch_decode(predicted_ids)[0]

            return audio_embedding, wav2vec_transcription

    async def _process_audio(self, input_data: MultiModalInput) -> Dict[str, Any]:
        """Process audio input with GPU-accelerated Whisper and Wav2Vec2 models. Issue #620."""
        torch = _get_torch()

        self._validate_audio_models_available()

        try:
            # Prepare audio data (Issue #315 - extracted method). #17778: an upload's
            # bytes are a FILE (WAV/webm/ogg/...): decode it first, off the loop.
            if isinstance(input_data.data, bytes):
                input_data = dataclasses.replace(input_data, data=await decode_audio_bytes_async(input_data.data))
            audio_array, sampling_rate = self._prepare_audio_data(input_data)

            # Process with Whisper for transcription (Issue #315 - extracted method)
            transcribed_text = await asyncio.to_thread(self._transcribe_with_whisper, audio_array, sampling_rate)

            # Issue #13104: Whisper answers silence with a confident phantom
            # phrase; drop it here so it never becomes a user turn downstream.
            transcribed_text = self._reject_silence_hallucination(transcribed_text, audio_array, sampling_rate)

            # Process with Wav2Vec2 for embeddings (Issue #315 - extracted method)
            audio_embedding, wav2vec_transcription = self._process_wav2vec_embeddings(audio_array, sampling_rate)

            # Determine command type from transcription
            command_type = self._classify_command(transcribed_text)

            # Clear GPU cache if using CUDA
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            # Build and return result (Issue #620 - extracted method)
            return self._build_voice_result(
                transcribed_text,
                wav2vec_transcription,
                command_type,
                audio_array,
                sampling_rate,
                audio_embedding,
            )

        except Exception as e:
            self.logger.error("Error during GPU-accelerated audio processing: %s", e)
            # Clear GPU cache on error
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            # Return error result (Issue #620 - extracted method)
            return self._build_error_result(e)

    def _reject_silence_hallucination(
        self,
        transcribed_text: str,
        audio_array: np.ndarray,
        sampling_rate: int,
    ) -> str:
        """Return "" when Whisper transcribed silence into a phantom phrase. Issue #13104.

        The language is whatever Whisper decided; the multilingual model does
        not surface it here, so only the language-independent energy and audio
        tag gates apply on this path.
        """
        if not transcribed_text:
            return transcribed_text

        rms = peak_window_rms(audio_array, sampling_rate)
        if not is_silence_hallucination(transcribed_text, rms=rms):
            return transcribed_text

        self.logger.info(
            "Discarded Whisper silence artifact %r instead of emitting a voice command (peak RMS %.5f)",
            transcribed_text,
            rms,
        )
        return ""

    def whisper_available(self) -> bool:
        """True when the one pinned Whisper pipeline is loaded or loadable; never loads it (#17778)."""
        return whisper_loadable()

    def _validate_audio_models_available(self) -> None:
        """Validate that audio models are loaded and available. Issue #620."""
        if not AUDIO_MODELS_AVAILABLE or not self.whisper_available() or self.wav2vec_model is None:
            self.logger.error("Audio models not available - cannot process voice")
            raise RuntimeError(
                "Voice processing unavailable: Required models (Whisper, Wav2Vec2) "
                "are not loaded. Ensure audio models are installed and GPU/NPU "
                "resources are available."
            )

    def _build_voice_result(
        self,
        transcribed_text: str,
        wav2vec_transcription: str,
        command_type: str,
        audio_array: np.ndarray,
        sampling_rate: int,
        audio_embedding: Any,
    ) -> Dict[str, Any]:
        """Build the voice processing result dictionary. Issue #620."""
        torch = _get_torch()

        result = {
            "type": "voice_command",
            "transcribed_text": transcribed_text,
            "wav2vec_transcription": wav2vec_transcription,
            "command_type": command_type,
            "confidence": 0.9 if transcribed_text else 0.0,
            "processing_device": whisper_device(),
            "wav2vec_device": str(self.device),
            "audio_duration_seconds": len(audio_array) / sampling_rate,
        }

        # Add audio embeddings if available
        if audio_embedding is not None:
            result["audio_embedding"] = audio_embedding.tolist()
            result["audio_embedding_shape"] = list(audio_embedding.shape)

        # Add GPU memory usage if CUDA is available
        if torch.cuda.is_available():
            result["gpu_memory_used_mb"] = torch.cuda.memory_allocated() / 1024 / 1024
            result["gpu_memory_cached_mb"] = torch.cuda.memory_reserved() / 1024 / 1024

        return result

    def _build_error_result(self, error: Exception) -> Dict[str, Any]:
        """Build error result dictionary for failed voice processing. Issue #620."""
        return {
            "type": "voice_command",
            "error": str(error),
            "transcribed_text": f"Processing failed: {str(error)}",
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
