# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Generic Speech Provider

Wraps existing AutoBot speech recognition (Google/Sphinx/Whisper)
for languages without specialized providers.
Part of Issue MVA-2185.
"""

from typing import List, Optional

from autobot_shared.logging_manager import get_logger
from voice_processing.models import AudioInput, SpeechRecognitionResult
from voice_processing.providers import SpeechProvider, TranscriptSegment
from voice_processing.speech_recognition import SpeechRecognitionEngine

logger = get_logger(__name__)


class GenericProvider(SpeechProvider):
    """Generic speech provider using AutoBot's existing recognition engine."""

    def __init__(self):
        """Initialize generic provider with speech recognition engine."""
        self.engine = SpeechRecognitionEngine()

    async def transcribe(
        self, audio_path: str, language: Optional[str] = None
    ) -> List[TranscriptSegment]:
        """Transcribe audio using generic recognition engine.

        Args:
            audio_path: Path to audio file
            language: BCP-47 language code (e.g., 'en', 'de')

        Returns:
            List of transcript segments
        """
        try:
            # Convert audio file to AudioInput
            # For MVP, we'll create a simple AudioInput
            # In production, this would properly load the audio file
            import os

            if not os.path.exists(audio_path):
                logger.error(f"Audio file not found: {audio_path}")
                return []

            # Create AudioInput from file
            # This is simplified - in production, we'd properly load audio data
            audio_input = await self._load_audio_input(audio_path)

            # Use existing speech recognition engine
            lang = language or "en"
            result: SpeechRecognitionResult = await self.engine.transcribe_audio(
                audio_input, language=lang
            )

            # Convert SpeechRecognitionResult to TranscriptSegments
            segments = self._convert_to_segments(result)
            logger.info(
                f"Generic provider transcription completed: "
                f"{len(segments)} segments"
            )
            return segments

        except Exception as e:
            logger.error(f"Generic provider transcription failed: {e}")
            return []

    async def _load_audio_input(self, audio_path: str) -> AudioInput:
        """Load audio file into AudioInput format.

        Args:
            audio_path: Path to audio file

        Returns:
            AudioInput object
        """
        import os
        import wave

        try:
            # Try to load as WAV file
            with wave.open(audio_path, 'rb') as wav:
                frames = wav.readframes(wav.getnframes())
                sample_rate = wav.getframerate()
                duration = wav.getnframes() / float(sample_rate)

                return AudioInput(
                    audio_id=os.path.basename(audio_path),
                    audio_data=frames,
                    sample_rate=sample_rate,
                    duration=duration,
                    metadata={"source_file": audio_path},
                )

        except Exception as e:
            logger.error(f"Failed to load audio file {audio_path}: {e}")
            # Return minimal AudioInput
            return AudioInput(
                audio_id=os.path.basename(audio_path),
                audio_data=b"",
                sample_rate=16000,
                duration=0.0,
                metadata={"source_file": audio_path, "load_error": str(e)},
            )

    def _convert_to_segments(
        self, result: SpeechRecognitionResult
    ) -> List[TranscriptSegment]:
        """Convert SpeechRecognitionResult to TranscriptSegments.

        Args:
            result: Speech recognition result

        Returns:
            List of transcript segments
        """
        segments = []

        # If we have speech segments with timing, use those
        if result.speech_segments:
            for seg in result.speech_segments:
                segments.append(
                    TranscriptSegment(
                        text=result.transcription,
                        start_time=seg.get("start_time", 0.0),
                        end_time=seg.get("end_time", 0.0),
                        confidence=result.confidence,
                        language=result.language,
                    )
                )
        else:
            # No timing information - create single segment
            segments.append(
                TranscriptSegment(
                    text=result.transcription,
                    start_time=0.0,
                    end_time=0.0,  # Unknown duration
                    confidence=result.confidence,
                    language=result.language,
                )
            )

        return segments

    @property
    def provider_name(self) -> str:
        """Return provider name."""
        return "Generic (Google/Sphinx)"

    @property
    def supported_languages(self) -> List[str]:
        """Return supported languages.

        Generic provider supports many languages via Google Speech API.
        """
        return [
            "en",  # English
            "de",  # German
            "es",  # Spanish
            "fr",  # French
            "ru",  # Russian
            "zh",  # Chinese
            "ja",  # Japanese
            "ko",  # Korean
            # Add more as needed
        ]
