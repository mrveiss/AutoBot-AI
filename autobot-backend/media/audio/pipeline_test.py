# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Audio Pipeline Tests
# Issue #932: Implement actual audio transcription

"""Unit tests for AudioPipeline."""

import base64
from unittest.mock import MagicMock, patch

import pytest
from media.audio.pipeline import AudioPipeline
from media.core.types import MediaInput, MediaType, ProcessingIntent


def _make_input(data, mime_type="audio/wav"):
    return MediaInput(
        media_id="test-audio",
        media_type=MediaType.AUDIO,
        intent=ProcessingIntent.ANALYSIS,
        data=data,
        mime_type=mime_type,
        metadata={"source": "test"},
    )


class TestAudioPipelineDecoding:
    """Tests for _decode_input helper."""

    def test_bytes_passthrough(self):
        pipe = AudioPipeline()
        raw = b"RIFF audio data"
        assert pipe._decode_input(raw) == raw

    def test_base64_string(self):
        pipe = AudioPipeline()
        raw = b"audio bytes"
        encoded = base64.b64encode(raw).decode()
        assert pipe._decode_input(encoded) == raw

    def test_unsupported_type_raises(self):
        pipe = AudioPipeline()
        with pytest.raises(ValueError, match="Unsupported"):
            pipe._decode_input(42)


class TestAudioPipelineSuffixMapping:
    """Tests for _suffix_from_mime."""

    def test_known_mimes(self):
        pipe = AudioPipeline()
        assert pipe._suffix_from_mime("audio/mpeg") == ".mp3"
        assert pipe._suffix_from_mime("audio/wav") == ".wav"
        assert pipe._suffix_from_mime("audio/ogg") == ".ogg"
        assert pipe._suffix_from_mime("audio/flac") == ".flac"
        assert pipe._suffix_from_mime("audio/webm") == ".webm"

    def test_unknown_mime_defaults_to_wav(self):
        pipe = AudioPipeline()
        assert pipe._suffix_from_mime("audio/unknown") == ".wav"
        assert pipe._suffix_from_mime("") == ".wav"


class TestAudioPipelineResults:
    """Tests for result-building helpers."""

    def test_transcription_result_with_text(self):
        pipe = AudioPipeline()
        result = pipe._transcription_result("Hello world", "en", [])
        assert result["type"] == "audio_transcription"
        assert result["transcribed_text"] == "Hello world"
        assert result["word_count"] == 2
        assert result["language"] == "en"
        assert result["processing_method"] == "whisper"
        assert result["confidence"] == 0.9

    def test_transcription_result_empty_text(self):
        pipe = AudioPipeline()
        result = pipe._transcription_result("", "unknown", [])
        assert result["word_count"] == 0
        assert result["confidence"] == 0.5

    def test_unavailable_result(self):
        pipe = AudioPipeline()
        result = pipe._unavailable_result({"source": "test"})
        assert result["processing_status"] == "unavailable"
        assert result["confidence"] == 0.0
        assert "transformers" in result["unavailability_reason"]

    def test_error_result(self):
        pipe = AudioPipeline()
        result = pipe._error_result("file not found", {"source": "test"})
        assert result["processing_status"] == "error"
        assert result["error"] == "file not found"
        assert result["confidence"] == 0.0


class TestAudioPipelineWhisper:
    """Tests for Whisper transcription path."""

    def test_returns_unavailable_when_transformers_missing(self):
        import asyncio

        pipe = AudioPipeline()

        async def _run():
            media_input = _make_input(b"fake audio")
            return await pipe._process_audio(media_input)

        with patch("media.audio.pipeline._TRANSFORMERS_AVAILABLE", False):
            result = asyncio.get_event_loop().run_until_complete(_run())
        assert result["processing_status"] == "unavailable"

    def test_run_whisper_writes_temp_file_and_cleans_up(self):
        pipe = AudioPipeline()
        deleted_paths = []

        def mock_unlink(path):
            deleted_paths.append(path)

        mock_pipe = MagicMock(
            return_value={
                "text": "hello world",
                "language": "en",
                "chunks": [],
            }
        )

        with patch("os.unlink", side_effect=mock_unlink):
            result = pipe._run_whisper(mock_pipe, b"fake audio bytes", "audio/wav")

        assert result["transcribed_text"] == "hello world"
        assert result["language"] == "en"
        assert len(deleted_paths) == 1  # temp file was cleaned up

    def test_run_whisper_handles_non_dict_output(self):
        pipe = AudioPipeline()
        mock_pipe = MagicMock(return_value="not a dict")

        with patch("os.unlink"):
            result = pipe._run_whisper(mock_pipe, b"bytes", "audio/wav")

        assert result["transcribed_text"] == ""
        assert result["language"] == "unknown"


class TestAudioPipelineAsync:
    """End-to-end async processing tests."""

    @pytest.mark.asyncio
    async def test_process_impl_unavailable(self):
        """When transformers not installed, process_impl succeeds with unavailable status."""
        pipe = AudioPipeline()
        media_input = _make_input(b"fake audio data")

        with patch("media.audio.pipeline._TRANSFORMERS_AVAILABLE", False):
            result = await pipe._process_impl(media_input)

        assert result.success is True
        assert result.result_data["processing_status"] == "unavailable"
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_process_impl_with_mock_whisper(self):
        """Mocked Whisper pipeline returns transcription result."""
        pipe = AudioPipeline()
        media_input = _make_input(b"fake audio data", "audio/wav")

        mock_whisper = MagicMock(
            return_value={
                "text": "test transcription",
                "language": "en",
                "chunks": [],
            }
        )

        with patch("media.audio.pipeline._TRANSFORMERS_AVAILABLE", True), patch(
            "media.audio.pipeline._whisper_pipeline", mock_whisper
        ), patch("os.unlink"):
            result = await pipe._process_impl(media_input)

        assert result.success is True
        assert result.result_data["transcribed_text"] == "test transcription"
        assert result.result_data["language"] == "en"
        assert result.confidence == 0.9
