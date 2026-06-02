# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Language Detection Service

Detects language from audio files for speech provider routing.
Part of Issue MVA-2185.
"""

import asyncio
import os
from typing import Optional

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


class LanguageDetectionService:
    """Service for detecting language from audio files."""

    def __init__(self):
        """Initialize language detection service."""
        self._detector = None
        self._initialize_detector()

    def _initialize_detector(self):
        """Initialize lingua language detector."""
        try:
            from lingua import Language, LanguageDetectorBuilder

            # Build detector with common languages
            # Add more languages as needed
            languages = [
                Language.ENGLISH,
                Language.LATVIAN,
                Language.RUSSIAN,
                Language.GERMAN,
                Language.SPANISH,
                Language.FRENCH,
            ]

            self._detector = LanguageDetectorBuilder.from_languages(*languages).build()
            logger.info(f"Language detector initialized with {len(languages)} languages")

        except ImportError:
            logger.warning("lingua-language-detector not installed - " "language detection disabled")
            self._detector = None

    async def detect_language(self, audio_path: str) -> Optional[str]:
        """Detect language from audio file.

        Args:
            audio_path: Path to audio file

        Returns:
            BCP-47 language code (e.g., 'lv', 'en') or None if detection fails
        """
        if not os.path.exists(audio_path):
            logger.error(f"Audio file not found: {audio_path}")
            return None

        if self._detector is None:
            logger.warning("Language detector not available, defaulting to 'en'")
            return "en"

        try:
            # For now, extract a sample of text from the audio
            # In production, this would use a speech-to-text model
            # to get a text sample, then detect language from that text
            text_sample = await self._extract_text_sample(audio_path)

            if not text_sample:
                logger.warning(f"Could not extract text sample from {audio_path}, " "defaulting to 'en'")
                return "en"

            # Detect language from text
            detected = self._detector.detect_language_of(text_sample)

            if detected is None:
                logger.warning("Language detection returned None, defaulting to 'en'")
                return "en"

            # Convert lingua Language enum to BCP-47 code
            lang_code = detected.iso_code_639_1.name.lower()
            logger.info(f"Detected language '{lang_code}' from audio: {audio_path}")
            return lang_code

        except Exception as e:
            logger.error(f"Language detection failed: {e}")
            return "en"  # Default to English on error

    async def _extract_text_sample(self, audio_path: str) -> Optional[str]:
        """Extract text sample from audio for language detection.

        This is a placeholder that would use a fast, lightweight
        speech-to-text model to get a text sample for language detection.

        For MVP, we'll use a simpler approach:
        - Try to detect from filename patterns
        - Use a fast Whisper model to get first few seconds of transcription

        Args:
            audio_path: Path to audio file

        Returns:
            Text sample or None
        """
        # Check filename for language hints
        filename = os.path.basename(audio_path).lower()

        if "latvian" in filename or "_lv_" in filename or "_lat_" in filename:
            return "latviešu valoda"  # Latvian text sample

        if "english" in filename or "_en_" in filename:
            return "english language"

        # If no hints in filename, we'd use a fast speech-to-text model here
        # For now, default to None (caller will use default language)
        logger.debug(f"No language hints in filename: {filename}, " "full transcription needed for detection")
        return None


# Singleton instance
_language_detection_service: Optional[LanguageDetectionService] = None


async def detect_language(audio_path: str, filename_hint: Optional[str] = None) -> Optional[str]:
    """Detect language from audio file via the singleton service."""
    return await get_language_detection_service().detect_language(audio_path)


def get_language_detection_service() -> LanguageDetectionService:
    """Get or create language detection service singleton."""
    global _language_detection_service
    if _language_detection_service is None:
        _language_detection_service = LanguageDetectionService()
    return _language_detection_service
