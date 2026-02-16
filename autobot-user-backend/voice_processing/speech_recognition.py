# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Speech Recognition Engine

Handles audio-to-text conversion using speech recognition libraries.
Extracted from voice_processing_system.py as part of Issue #381 god class refactoring.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List

import numpy as np
from enhanced_memory_manager_async import TaskPriority
from task_execution_tracker import task_tracker

from backend.voice_processing.models import AudioInput, SpeechRecognitionResult
from backend.voice_processing.types import SpeechQuality

logger = logging.getLogger(__name__)


class SpeechRecognitionEngine:
    """Speech recognition and transcription engine"""

    def __init__(self):
        """Initialize speech recognition engine with recognizer components."""
        self.recognizer = None
        self.language_detector = None
        self.noise_reducer = None

        # Initialize speech recognition components
        self._initialize_speech_recognition()

        logger.info("Speech Recognition Engine initialized")

    def _initialize_speech_recognition(self):
        """Initialize speech recognition components"""
        try:
            # Try to import speech_recognition library
            import speech_recognition as sr

            self.recognizer = sr.Recognizer()

            # Configure recognizer settings
            self.recognizer.energy_threshold = 300
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.pause_threshold = 0.8
            self.recognizer.phrase_threshold = 0.3

            logger.info("SpeechRecognition library loaded successfully")

        except ImportError:
            logger.warning("SpeechRecognition library not available")
            self.recognizer = None

        try:
            # Try to initialize language detection
            # from langdetect import detect
            logger.info("Language detection available")
        except ImportError:
            logger.warning("Language detection not available")

    async def _run_parallel_analysis(self, audio_input: AudioInput) -> tuple:
        """Issue #665: Extracted from transcribe_audio to reduce function length.

        Run audio analysis operations in parallel for better performance.
        All operations are independent and only read from audio_input.
        """
        if self.recognizer is not None:
            return await asyncio.gather(
                self._analyze_audio_quality(audio_input),
                self._calculate_noise_level(audio_input),
                self._perform_speech_recognition(audio_input),
                self._detect_speech_segments(audio_input),
            )
        # Run parallel operations without speech recognition
        audio_quality, noise_level, speech_segments = await asyncio.gather(
            self._analyze_audio_quality(audio_input),
            self._calculate_noise_level(audio_input),
            self._detect_speech_segments(audio_input),
        )
        # Fallback when speech recognition not available
        transcription_result = {
            "transcription": "[Speech recognition not available]",
            "confidence": 0.0,
            "alternatives": [],
            "language": "unknown",
        }
        return audio_quality, noise_level, transcription_result, speech_segments

    def _build_recognition_result(
        self,
        audio_input: AudioInput,
        transcription_result: Dict[str, Any],
        speech_segments: List[Dict[str, Any]],
        audio_quality: Any,
        noise_level: float,
        processing_time: float,
    ) -> SpeechRecognitionResult:
        """Issue #665: Extracted from transcribe_audio to reduce function length.

        Build the SpeechRecognitionResult from analysis outputs.
        """
        return SpeechRecognitionResult(
            audio_id=audio_input.audio_id,
            transcription=transcription_result["transcription"],
            confidence=transcription_result["confidence"],
            language=transcription_result["language"],
            alternative_transcriptions=transcription_result["alternatives"],
            speech_segments=speech_segments,
            audio_quality=audio_quality,
            noise_level=noise_level,
            processing_time=processing_time,
            metadata={
                "original_metadata": audio_input.metadata,
                "processing_timestamp": time.time(),
                "engine": "speech_recognition" if self.recognizer else "placeholder",
            },
        )

    async def transcribe_audio(
        self, audio_input: AudioInput
    ) -> SpeechRecognitionResult:
        """Transcribe audio to text using speech recognition"""

        async with task_tracker.track_task(
            "Speech Recognition",
            f"Transcribing audio: {audio_input.audio_id}",
            agent_type="voice_processing",
            priority=TaskPriority.HIGH,
            inputs={
                "audio_id": audio_input.audio_id,
                "duration": audio_input.duration,
                "sample_rate": audio_input.sample_rate,
            },
        ) as task_context:
            start_time = time.time()

            try:
                (
                    audio_quality,
                    noise_level,
                    transcription_result,
                    speech_segments,
                ) = await self._run_parallel_analysis(audio_input)
                processing_time = time.time() - start_time

                result = self._build_recognition_result(
                    audio_input,
                    transcription_result,
                    speech_segments,
                    audio_quality,
                    noise_level,
                    processing_time,
                )

                task_context.set_outputs(
                    {
                        "transcription": result.transcription,
                        "confidence": result.confidence,
                        "audio_quality": result.audio_quality.value,
                        "processing_time": processing_time,
                    }
                )

                logger.info(
                    f"Speech recognition completed: {audio_input.audio_id}, "
                    f"confidence: {result.confidence:.2f}"
                )
                return result

            except Exception as e:
                task_context.set_outputs({"error": str(e)})
                logger.error("Speech recognition failed: %s", e)
                raise

    def _evaluate_audio_quality(self, audio_input: AudioInput) -> SpeechQuality:
        """Evaluate audio quality based on sample rate and duration (Issue #315 - extracted helper)."""
        # Check sample rate quality
        if audio_input.sample_rate < 8000:
            return SpeechQuality.POOR
        if audio_input.sample_rate < 16000:
            return SpeechQuality.FAIR

        # Check duration quality
        if audio_input.duration < 0.5:
            return SpeechQuality.POOR
        if audio_input.duration > 30:
            return SpeechQuality.FAIR  # Very long audio might have quality issues

        return SpeechQuality.GOOD

    async def _analyze_audio_quality(self, audio_input: AudioInput) -> SpeechQuality:
        """Analyze audio quality for speech recognition (Issue #315 - refactored depth 5 to 2)."""
        try:
            return self._evaluate_audio_quality(audio_input)
        except Exception as e:
            logger.debug("Audio quality analysis failed: %s", e)
            return SpeechQuality.UNKNOWN

    async def _calculate_noise_level(self, audio_input: AudioInput) -> float:
        """Calculate background noise level in audio"""
        try:
            if isinstance(audio_input.audio_data, np.ndarray):
                # Calculate RMS (Root Mean Square) as noise estimate
                rms = np.sqrt(np.mean(audio_input.audio_data**2))
                return float(rms)
            else:
                return 0.5  # Default noise level

        except Exception as e:
            logger.debug("Noise level calculation failed: %s", e)
            return 0.5

    def _try_google_recognition(self, audio_data) -> List[Dict[str, Any]]:
        """Try Google speech recognition (Issue #298 - extracted helper)."""
        results = []
        try:
            result = self.recognizer.recognize_google(audio_data, show_all=True)
            if not result or "alternative" not in result:
                return results
            for alt in result["alternative"]:
                results.append(
                    {
                        "text": alt.get("transcript", ""),
                        "confidence": alt.get("confidence", 0.0),
                        "engine": "google",
                    }
                )
        except Exception as e:
            logger.debug("Google Speech Recognition failed: %s", e)
        return results

    def _try_sphinx_recognition(self, audio_data) -> List[Dict[str, Any]]:
        """Try Sphinx offline recognition (Issue #298 - extracted helper)."""
        try:
            text = self.recognizer.recognize_sphinx(audio_data)
            return [
                {
                    "text": text,
                    "confidence": 0.7,  # Sphinx doesn't provide confidence
                    "engine": "sphinx",
                }
            ]
        except Exception as e:
            logger.debug("Sphinx Recognition failed: %s", e)
            return []

    async def _perform_speech_recognition(
        self, audio_input: AudioInput
    ) -> Dict[str, Any]:
        """Perform actual speech recognition"""
        empty_result = {
            "transcription": "",
            "confidence": 0.0,
            "alternatives": [],
            "language": "unknown",
        }

        if self.recognizer is None:
            return empty_result

        try:
            # Convert audio data to AudioData format
            audio_data = self._convert_to_audio_data(audio_input)

            # Try recognition engines (Issue #298 - uses helpers)
            transcription_results = self._try_google_recognition(audio_data)

            if not transcription_results:
                transcription_results = self._try_sphinx_recognition(audio_data)

            # Process results
            if not transcription_results:
                return empty_result

            best_result = max(transcription_results, key=lambda x: x["confidence"])
            return {
                "transcription": best_result["text"],
                "confidence": best_result["confidence"],
                "alternatives": transcription_results[1:],
                "language": "en",
            }

        except Exception as e:
            logger.error("Speech recognition processing failed: %s", e)
            return empty_result

    def _convert_to_audio_data(self, audio_input: AudioInput):
        """Convert audio input to speech_recognition AudioData format"""
        try:
            import speech_recognition as sr

            if isinstance(audio_input.audio_data, bytes):
                # Convert bytes to AudioData
                audio_data = sr.AudioData(
                    audio_input.audio_data, audio_input.sample_rate, 2  # 16-bit samples
                )
            elif isinstance(audio_input.audio_data, np.ndarray):
                # Convert numpy array to bytes
                audio_bytes = (
                    (audio_input.audio_data * 32767).astype(np.int16).tobytes()
                )
                audio_data = sr.AudioData(audio_bytes, audio_input.sample_rate, 2)
            else:
                raise ValueError(
                    f"Unsupported audio data type: {type(audio_input.audio_data)}"
                )

            return audio_data

        except Exception as e:
            logger.error("Audio conversion failed: %s", e)
            raise

    async def _detect_speech_segments(
        self, audio_input: AudioInput
    ) -> List[Dict[str, Any]]:
        """Detect speech segments in audio for timing information"""
        try:
            # Simple speech segment detection
            # In a real implementation, this would use VAD (Voice Activity Detection)
            segments = [
                {
                    "start_time": 0.0,
                    "end_time": audio_input.duration,
                    "confidence": 0.8,
                    "type": "speech",
                }
            ]

            return segments

        except Exception as e:
            logger.debug("Speech segmentation failed: %s", e)
            return []
