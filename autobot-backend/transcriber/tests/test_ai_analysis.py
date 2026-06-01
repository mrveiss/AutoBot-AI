# autobot-backend/transcriber/tests/test_ai_analysis.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import pytest
from transcriber.ai.context import build_context
from transcriber.ai.prompts import get_system_prompt


def test_build_context_formats_segments():
    segments = [
        {"start": 0.0, "end": 1.5, "speaker_name": "Alice", "text": "Hello"},
        {"start": 1.5, "end": 3.0, "speaker_name": "Bob", "text": "World"},
    ]
    ctx = build_context(segments, max_chars=5000)
    assert "Alice" in ctx
    assert "Hello" in ctx
    assert "00:00:00" in ctx


def test_build_context_truncates_at_max():
    segments = [{"start": float(i), "end": float(i+1), "speaker_name": "A", "text": "X" * 100}
                for i in range(200)]
    ctx = build_context(segments, max_chars=500)
    assert len(ctx) <= 600  # some slack for truncation message


def test_get_system_prompt_summarize():
    p = get_system_prompt("summarize")
    assert len(p) > 20


def test_get_system_prompt_custom():
    p = get_system_prompt("custom", custom_question="What was agreed?")
    assert "What was agreed?" in p
