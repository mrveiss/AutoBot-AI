# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for Language Detection Service

Tests language detection from audio files and filename hints.
Part of Issue MVA-2185.

Every filename these tests hand to the detector is fixed, inside pytest's
``tmp_path`` (#16341). ``tempfile.NamedTemporaryFile`` draws its random part
from ``a-z0-9_``, and ``_filename_tokens`` in ``language_detection.py`` splits
on exactly those non-alphanumeric separators -- so a random name can, by
chance, isolate a token that reads as a language hint nobody asked for. Seen
in CI: ``test_no_filename_hint`` got a random ``tmpq_lv_3k.wav`` and the
service correctly found ``lv`` in it, failing an assertion that expected no
hint at all. A fixed name removes the randomness the assertions never meant
to depend on.
"""

import asyncio

import pytest

from voice_processing.language_detection import (
    LanguageDetectionService,
    get_language_detection_service,
)


class TestLanguageDetectionService:
    """Test language detection functionality."""

    def test_initialization(self):
        """Test service initializes without errors."""
        service = LanguageDetectionService()
        assert service is not None

    @pytest.mark.asyncio
    async def test_detect_from_filename_latvian(self, tmp_path):
        """Test detection from Latvian filename hints."""
        service = LanguageDetectionService()

        temp_path = str(tmp_path / "clip_lv_audio.wav")

        sample = await service._extract_text_sample(temp_path)
        assert sample == "latviešu valoda"

    @pytest.mark.asyncio
    async def test_detect_from_filename_english(self, tmp_path):
        """Test detection from English filename hints."""
        service = LanguageDetectionService()

        temp_path = str(tmp_path / "clip_en_audio.wav")

        sample = await service._extract_text_sample(temp_path)
        assert sample == "english language"

    @pytest.mark.asyncio
    async def test_missing_file(self):
        """Test handling of missing audio file."""
        service = LanguageDetectionService()

        result = await service.detect_language("/nonexistent/file.wav")
        assert result is None

    @pytest.mark.asyncio
    async def test_no_filename_hint(self, tmp_path):
        """Test fallback when no filename hints."""
        service = LanguageDetectionService()

        temp_path = str(tmp_path / "recording.wav")

        sample = await service._extract_text_sample(temp_path)
        # Should return None when no hints
        assert sample is None

    @pytest.mark.asyncio
    async def test_default_to_english(self, tmp_path):
        """Test that detection defaults to English on failure."""
        service = LanguageDetectionService()

        temp_path = tmp_path / "recording.wav"
        # Write minimal valid WAV header: RIFF magic, zeroed file size, WAVE format
        await asyncio.to_thread(temp_path.write_bytes, b"RIFF\x00\x00\x00\x00WAVE")

        result = await service.detect_language(str(temp_path))
        # Should default to 'en' when detection fails
        assert result == "en"


class TestGlobalService:
    """Test global service singleton."""

    def test_get_language_detection_service_singleton(self):
        """Test that get_language_detection_service returns same instance."""
        service1 = get_language_detection_service()
        service2 = get_language_detection_service()
        assert service1 is service2

    def test_service_not_none(self):
        """Test that global service is not None."""
        service = get_language_detection_service()
        assert service is not None


class TestFilenamePatterns:
    """Test various filename patterns for language hints."""

    @pytest.mark.asyncio
    async def test_latvian_patterns(self, tmp_path):
        """Test various Latvian filename patterns."""
        service = LanguageDetectionService()

        patterns = [
            "recording_lv_20260601.wav",
            "latvian_interview.wav",
            "meeting_lat_final.wav",
            "audio_LV.wav",
        ]

        for pattern in patterns:
            temp_path = str(tmp_path / pattern)

            sample = await service._extract_text_sample(temp_path)
            # #13162: every listed pattern must resolve. The previous
            # "or '_lv_' in path" clause passed vacuously for the patterns
            # that already contained a separator on both sides, hiding the
            # fact that a trailing code ("audio_LV.wav") never matched.
            assert sample == "latviešu valoda", f"no Latvian hint from {pattern}"

    @pytest.mark.asyncio
    async def test_english_patterns(self, tmp_path):
        """Test various English filename patterns."""
        service = LanguageDetectionService()

        patterns = [
            "recording_en_20260601.wav",
            "english_interview.wav",
            "meeting_EN.wav",
        ]

        for pattern in patterns:
            temp_path = str(tmp_path / pattern)

            sample = await service._extract_text_sample(temp_path)
            # #13162: see test_latvian_patterns — the escape-hatch clause
            # made "meeting_EN.wav" pass without ever matching.
            assert sample == "english language", f"no English hint from {pattern}"
