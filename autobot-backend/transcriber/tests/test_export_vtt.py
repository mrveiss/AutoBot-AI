# autobot-backend/transcriber/tests/test_export_vtt.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
from transcriber.export.vtt_export import segments_to_vtt


def test_vtt_starts_with_webvtt():
    segments = [{"start": 0.0, "end": 1.0, "text": "Hello", "speaker": "Alice"}]
    result = segments_to_vtt(segments, include_speaker=True)
    assert result.startswith("WEBVTT")


def test_vtt_timestamp_format():
    segments = [{"start": 65.5, "end": 70.123, "text": "Test", "speaker": "Bob"}]
    result = segments_to_vtt(segments, include_speaker=False)
    assert "00:01:05.500 --> 00:01:10.123" in result
