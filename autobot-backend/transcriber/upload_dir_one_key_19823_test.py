# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#19823: uploads are written where the path guard allows, from one key."""

from __future__ import annotations

from pathlib import Path

import pytest

from transcriber import orchestrator, upload_security


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("TRANSCRIBER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(upload_security, "_configured_upload_dir", lambda: "")
    return tmp_path / "data"


def test_the_default_is_under_the_transcriber_data_dir(data_dir: Path) -> None:
    assert upload_security.get_upload_base_dir() == (data_dir / "uploads").resolve()


def test_the_configured_key_wins(data_dir: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(upload_security, "_configured_upload_dir", lambda: str(tmp_path / "elsewhere"))
    assert upload_security.get_upload_base_dir() == (tmp_path / "elsewhere").resolve()


def test_a_fixture_written_to_the_upload_dir_passes_the_guard(data_dir: Path) -> None:
    fixture = upload_security.get_upload_base_dir() / "clip.wav"
    fixture.write_bytes(b"RIFF")
    orchestrator._validate_file_path(str(fixture))


def test_contrast_a_file_outside_it_is_refused(data_dir: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"RIFF")
    with pytest.raises(ValueError):
        orchestrator._validate_file_path(str(outside))


def test_the_startup_sets_the_upload_dir_from_the_one_resolver() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "initialization" / "lifespan.py").read_text(encoding="utf-8")
    assert "app.state.transcriber_upload_dir = str(upload_dir)" in source
    assert "upload_dir = get_upload_base_dir()" in source
