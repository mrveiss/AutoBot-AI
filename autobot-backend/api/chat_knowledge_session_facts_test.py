# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Coverage for the ``category`` default in ``get_session_facts`` (#14047)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.chat_knowledge import get_session_facts
from constants.threshold_constants import CategoryDefaults


def _request_with_facts(facts):
    kb = SimpleNamespace(get_facts_by_session=AsyncMock(return_value=facts))
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(knowledge_base=kb)))


@pytest.mark.asyncio
async def test_missing_category_defaults_to_general():
    request = _request_with_facts([{"id": "f1", "content": "hi"}])

    result = await get_session_facts("session-1", request)

    assert result["facts"][0]["category"] == CategoryDefaults.GENERAL


@pytest.mark.asyncio
async def test_explicit_category_overrides_default():
    request = _request_with_facts([{"id": "f1", "content": "hi", "category": "security"}])

    result = await get_session_facts("session-1", request)

    assert result["facts"][0]["category"] == "security"
