# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/transcriber/tests/test_export_vtt.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
from transcriber.export.vtt_export import segments_to_vtt


def test_vtt_starts_with_webvtt():
    segments = [{"start_time": 0.0, "end_time": 1.0, "text": "Hello", "speaker_name": "Alice"}]
    result = segments_to_vtt(segments, include_speaker=True)
    assert result.startswith("WEBVTT")


def test_vtt_timestamp_format():
    segments = [{"start_time": 65.5, "end_time": 70.123, "text": "Test", "speaker_name": "Bob"}]
    result = segments_to_vtt(segments, include_speaker=False)
    assert "00:01:05.500 --> 00:01:10.123" in result
