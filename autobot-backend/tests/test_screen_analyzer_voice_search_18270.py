# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for voice-guided screen search (Issue #18270)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest

from autobot_shared.embedding_model import EmbeddingUnavailableError
from computer_vision.screen_analyzer import ScreenAnalyzer


@pytest.mark.asyncio
async def test_voice_search_uses_initialized_engine_singleton(monkeypatch):
    engine = SimpleNamespace(cross_modal_search=AsyncMock(return_value={"image": []}))
    get_engine = AsyncMock(return_value=engine)
    monkeypatch.setattr("npu_semantic_search.get_npu_search_engine", get_engine)

    analyzer = ScreenAnalyzer.__new__(ScreenAnalyzer)
    analyzer._map_search_to_ui_elements = AsyncMock(return_value=[])
    screenshot = np.zeros((2, 2, 3), dtype=np.uint8)

    result = await analyzer.find_elements_by_voice_description("search box", screenshot)

    assert result == []
    get_engine.assert_awaited_once_with()
    engine.cross_modal_search.assert_awaited_once_with(
        query="search box",
        query_modality="text",
        target_modalities=["image"],
        limit=10,
        similarity_threshold=0.7,
    )
    analyzer._map_search_to_ui_elements.assert_awaited_once_with({"image": []}, screenshot)


@pytest.mark.asyncio
async def test_voice_search_surfaces_embedding_refusal(monkeypatch):
    refusal = EmbeddingUnavailableError("image embedding space is not recorded")
    engine = SimpleNamespace(cross_modal_search=AsyncMock(side_effect=refusal))
    monkeypatch.setattr("npu_semantic_search.get_npu_search_engine", AsyncMock(return_value=engine))

    analyzer = ScreenAnalyzer.__new__(ScreenAnalyzer)
    analyzer._map_search_to_ui_elements = AsyncMock()
    screenshot = np.zeros((2, 2, 3), dtype=np.uint8)

    with pytest.raises(EmbeddingUnavailableError, match="not recorded"):
        await analyzer.find_elements_by_voice_description("search box", screenshot)

    analyzer._map_search_to_ui_elements.assert_not_awaited()
