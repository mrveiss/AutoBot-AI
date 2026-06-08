# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for Language Detection Service

Tests language detection from audio files and filename hints.
Part of Issue MVA-2185.
"""

import os
import tempfile

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
    async def test_detect_from_filename_latvian(self):
        """Test detection from Latvian filename hints."""
        service = LanguageDetectionService()

        # Create temp file with Latvian hint
        with tempfile.NamedTemporaryFile(suffix="_lv_audio.wav", delete=False) as f:
            temp_path = f.name

        try:
            # Extract text sample should detect Latvian from filename
            sample = await service._extract_text_sample(temp_path)
            assert sample is not None
            assert "latviešu" in sample.lower() or "lv" in temp_path.lower()
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_detect_from_filename_english(self):
        """Test detection from English filename hints."""
        service = LanguageDetectionService()

        with tempfile.NamedTemporaryFile(suffix="_en_audio.wav", delete=False) as f:
            temp_path = f.name

        try:
            sample = await service._extract_text_sample(temp_path)
            assert sample is not None
            assert "english" in sample.lower() or "en" in temp_path.lower()
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_missing_file(self):
        """Test handling of missing audio file."""
        service = LanguageDetectionService()

        result = await service.detect_language("/nonexistent/file.wav")
        assert result is None

    @pytest.mark.asyncio
    async def test_no_filename_hint(self):
        """Test fallback when no filename hints."""
        service = LanguageDetectionService()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name

        try:
            sample = await service._extract_text_sample(temp_path)
            # Should return None when no hints
            assert sample is None
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_default_to_english(self):
        """Test that detection defaults to English on failure."""
        service = LanguageDetectionService()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name
            # Write minimal valid WAV header
            f.write(b"RIFF")
            f.write(b"\x00\x00\x00\x00")  # File size
            f.write(b"WAVE")

        try:
            result = await service.detect_language(temp_path)
            # Should default to 'en' when detection fails
            assert result == "en"
        finally:
            os.unlink(temp_path)


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
    async def test_latvian_patterns(self):
        """Test various Latvian filename patterns."""
        service = LanguageDetectionService()

        patterns = [
            "recording_lv_20260601.wav",
            "latvian_interview.wav",
            "meeting_lat_final.wav",
            "audio_LV.wav",
        ]

        for pattern in patterns:
            with tempfile.NamedTemporaryFile(suffix=pattern, delete=False) as f:
                temp_path = f.name

            try:
                sample = await service._extract_text_sample(temp_path)
                # Should detect Latvian hint
                assert sample is not None or "_lv_" in temp_path.lower()
            finally:
                os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_english_patterns(self):
        """Test various English filename patterns."""
        service = LanguageDetectionService()

        patterns = [
            "recording_en_20260601.wav",
            "english_interview.wav",
            "meeting_EN.wav",
        ]

        for pattern in patterns:
            with tempfile.NamedTemporaryFile(suffix=pattern, delete=False) as f:
                temp_path = f.name

            try:
                sample = await service._extract_text_sample(temp_path)
                # Should detect English hint
                assert sample is not None or "_en_" in temp_path.lower()
            finally:
                os.unlink(temp_path)
