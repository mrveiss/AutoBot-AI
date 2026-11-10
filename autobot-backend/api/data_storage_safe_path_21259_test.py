# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``_safe_data_path`` never builds a path from the request string for the legacy category (#21259)."""

import pytest
from fastapi import HTTPException

import api.data_storage as data_storage
from api.data_storage_categories import LEGACY_TRANSCRIPTS_CATEGORY
from autobot_shared.ssot_config import config


def test_legacy_category_resolves_outside_data_dir_via_constant(tmp_path, monkeypatch) -> None:
    directory = (tmp_path / "elsewhere" / "conversation_transcripts").resolve()
    monkeypatch.setattr(config.path, "legacy_transcripts_dir", str(directory))
    seen = []
    real = data_storage.category_dir

    def spy(base, segment):
        seen.append(segment)
        return real(base, segment)

    monkeypatch.setattr(data_storage, "category_dir", spy)
    assert data_storage._safe_data_path(LEGACY_TRANSCRIPTS_CATEGORY) == directory
    assert seen == [LEGACY_TRANSCRIPTS_CATEGORY]
    assert directory != data_storage.DATA_DIR / LEGACY_TRANSCRIPTS_CATEGORY


@pytest.mark.parametrize("segment", ["../x", "/etc/passwd", "a/../../x"])
def test_traversal_segments_are_rejected(segment) -> None:
    with pytest.raises(HTTPException):
        data_storage._safe_data_path(segment)


def test_non_legacy_category_stays_under_data_dir() -> None:
    result = data_storage._safe_data_path("logs")
    assert result == (data_storage.DATA_DIR / "logs").resolve()


@pytest.mark.parametrize("segment", ["..%2fx", "%2e%2e/x"])
def test_encoded_traversal_is_never_decoded_so_stays_contained(segment) -> None:
    result = data_storage._safe_data_path(segment)
    assert result.is_relative_to(data_storage.DATA_DIR.resolve())
