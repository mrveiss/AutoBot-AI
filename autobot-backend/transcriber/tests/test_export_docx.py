# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/transcriber/tests/test_export_docx.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
import pytest

pytest.importorskip("docx", reason="python-docx not installed")
from transcriber.export.docx_export import build_docx


def test_build_docx_returns_bytes():
    segments = [
        {"start": 0.0, "end": 1.5, "text": "Hello", "speaker_name": "Alice", "notes": []},
    ]
    result = build_docx(
        title="Test Recording",
        segments=segments,
        include_timestamps=True,
        include_notes=True,
        include_speaker_names=True,
    )
    assert isinstance(result, bytes)
    # DOCX files start with PK (zip magic bytes)
    assert result[:2] == b"PK"


def test_build_docx_without_timestamps():
    segments = [{"start": 0.0, "end": 1.0, "text": "Hi", "speaker_name": "Bob", "notes": []}]
    result = build_docx(
        title="Test",
        segments=segments,
        include_timestamps=False,
        include_notes=False,
        include_speaker_names=True,
    )
    assert isinstance(result, bytes)
