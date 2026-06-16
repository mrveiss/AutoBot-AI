# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/transcriber/tests/test_export_srt.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
from transcriber.export.srt_export import segments_to_srt


def test_srt_basic_format():
    segments = [
        {"start_time": 0.0, "end_time": 1.5, "text": "Hello", "speaker_name": "Alice"},
        {"start_time": 1.5, "end_time": 3.0, "text": "World", "speaker_name": "Bob"},
    ]
    result = segments_to_srt(segments, include_speaker=True)
    assert "00:00:00,000 --> 00:00:01,500" in result
    assert "Alice: Hello" in result
    assert "2\n" in result


def test_srt_without_speaker():
    segments = [{"start_time": 0.0, "end_time": 1.0, "text": "Hi", "speaker_name": "Alice"}]
    result = segments_to_srt(segments, include_speaker=False)
    assert "Alice" not in result
    assert "Hi" in result


def test_srt_empty():
    assert segments_to_srt([], include_speaker=True) == ""
