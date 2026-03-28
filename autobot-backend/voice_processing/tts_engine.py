# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Text-to-Speech Engine

Handles text-to-speech synthesis for voice responses.
Extracted from voice_processing_system.py as part of Issue #381 god class refactoring.
"""

import asyncio
import logging

import aiofiles

from task_execution_tracker import task_tracker
from voice_processing.models import SpeechSynthesisRequest

logger = logging.getLogger(__name__)


class TextToSpeechEngine:
    """Text-to-speech synthesis engine"""

    def __init__(self):
        """Initialize TTS engine with default voice settings."""
        self.tts_engine = None
        self.voice_settings = {"rate": 150, "volume": 0.8, "voice_id": "default"}

        self._initialize_tts_engine()
        logger.info("Text-to-Speech Engine initialized")

    def _initialize_tts_engine(self):
        """Initialize TTS engine"""
        try:
            # Try pyttsx3 for offline TTS
            import pyttsx3

            self.tts_engine = pyttsx3.init()

            # Configure voice settings
            self.tts_engine.setProperty("rate", self.voice_settings["rate"])
            self.tts_engine.setProperty("volume", self.voice_settings["volume"])

            logger.info("pyttsx3 TTS engine initialized")

        except ImportError:
            logger.warning("pyttsx3 not available, TTS will be limited")
            self.tts_engine = None
        except Exception as e:
            logger.error("TTS engine initialization failed: %s", e)
            self.tts_engine = None

    async def synthesize_speech(self, request: SpeechSynthesisRequest) -> bytes:
        """Convert text to speech audio"""

        async with task_tracker.track_task(
            "Speech Synthesis",
            f"Converting text to speech: {request.text[:50]}...",
            agent_type="voice_processing",
            priority=request.priority,
            inputs={
                "text_length": len(request.text),
                "output_format": request.output_format,
            },
        ) as task_context:
            try:
                if self.tts_engine is None:
                    # Return empty audio data when TTS not available
                    task_context.set_outputs({"error": "TTS engine not available"})
                    return b""

                # Apply voice settings from request
                if "rate" in request.voice_settings:
                    self.tts_engine.setProperty("rate", request.voice_settings["rate"])

                if "volume" in request.voice_settings:
                    self.tts_engine.setProperty(
                        "volume", request.voice_settings["volume"]
                    )

                # Generate speech
                if request.output_format.lower() == "wav":
                    audio_data = await self._generate_wav_audio(request.text)
                else:
                    audio_data = await self._generate_default_audio(request.text)

                task_context.set_outputs(
                    {
                        "audio_size": len(audio_data),
                        "format": request.output_format,
                        "success": len(audio_data) > 0,
                    }
                )

                logger.info(
                    f"Speech synthesis completed: {len(audio_data)} bytes generated"
                )
                return audio_data

            except Exception as e:
                task_context.set_outputs({"error": str(e)})
                logger.error("Speech synthesis failed: %s", e)
                return b""

    async def _generate_wav_audio(self, text: str) -> bytes:
        """Generate WAV audio data"""
        try:
            import os
            import tempfile

            # Create temporary file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_path = temp_file.name

            # Generate speech to file (blocking TTS operation)
            await asyncio.to_thread(self.tts_engine.save_to_file, text, temp_path)
            await asyncio.to_thread(self.tts_engine.runAndWait)

            # Read file content asynchronously
            try:
                async with aiofiles.open(temp_path, "rb") as audio_file:
                    audio_data = await audio_file.read()
            except OSError as e:
                logger.error("Failed to read audio file %s: %s", temp_path, e)
                return b""

            # Clean up
            await asyncio.to_thread(os.unlink, temp_path)

            return audio_data

        except Exception as e:
            logger.error("WAV audio generation failed: %s", e)
            return b""

    async def _generate_default_audio(self, text: str) -> bytes:
        """Generate audio in default format"""
        # For now, return empty bytes when specific format not supported
        logger.warning("Default audio format not implemented")
        return b""
