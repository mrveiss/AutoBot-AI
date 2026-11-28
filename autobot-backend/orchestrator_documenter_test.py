# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Orchestrator._get_documenter resolves the canonical KnowledgeBase (#18122)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator import Orchestrator

#: The globals ``_get_documenter`` actually reads. ``patch("orchestrator.<name>")`` targets
#: whatever module sits in ``sys.modules`` NOW, which a suite that reloads it can replace.
_G = Orchestrator._get_documenter.__globals__


def _bare_orchestrator(knowledge_base=None) -> Orchestrator:
    orch = Orchestrator.__new__(Orchestrator)
    orch.knowledge_base = knowledge_base
    orch.llm_service = MagicMock()
    orch._documenter = None
    return orch


@pytest.mark.asyncio
async def test_cached_documenter_without_kb_adopts_canonical_kb_once_up():
    orch = _bare_orchestrator()
    canonical = MagicMock()
    accessor = AsyncMock(side_effect=[None, canonical])
    documenter_cls = MagicMock(return_value=MagicMock(knowledge_base=None))
    names = {"get_knowledge_base_async": accessor, "KNOWLEDGE_BASE_AVAILABLE": True}
    with patch.dict(_G, {**names, "WorkflowDocumenter": documenter_cls}):
        first = await orch._get_documenter()
        assert first.knowledge_base is None  # init failed: built without a KB

        second = await orch._get_documenter()

    assert second is first
    assert second.knowledge_base is canonical
    documenter_cls.assert_called_once()


@pytest.mark.asyncio
async def test_cached_documenter_with_kb_is_not_replaced():
    orch = _bare_orchestrator()
    existing = MagicMock()
    orch._documenter = MagicMock(knowledge_base=existing)
    accessor = AsyncMock(return_value=MagicMock())
    with patch.dict(_G, {"get_knowledge_base_async": accessor, "KNOWLEDGE_BASE_AVAILABLE": True}):
        documenter = await orch._get_documenter()
    assert documenter.knowledge_base is existing
