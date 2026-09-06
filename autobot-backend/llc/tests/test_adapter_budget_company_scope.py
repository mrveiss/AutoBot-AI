# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The adapter must not charge a budget it cannot name (#15812).

Lives in its own file rather than in `test_autobot_agent_adapter.py` because
that file is grandfathered at a recorded size ceiling (#14236) and a
grandfathered file may not grow. The ceiling refusing the addition is the
reason this test is where it is.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from llc.adapters.autobot_agent_adapter import AutoBotAgentAdapter
from llc.tests.test_autobot_agent_adapter import _FAKE_AGENT_PATH


@pytest.mark.asyncio
async def test_cost_is_not_charged_without_a_company():
    """No company in context means no budget row can be named, so nothing is charged.

    Guessing would mean charging whichever company happened to hold the slug, which
    is precisely the confusion #15812 exists to remove. Refusing loudly is the only
    honest option, and it is asserted here so a later "helpful" fallback cannot be
    added silently.
    """
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    def session_factory():
        return mock_session

    with patch("llc.services.budget.BudgetService") as MockBS:
        MockBS.return_value.ingest_cost_event = AsyncMock()

        adapter = AutoBotAgentAdapter(
            {"agent_class": _FAKE_AGENT_PATH},
            budget_session_factory=session_factory,
        )
        run_id = await adapter.invoke({}, {"title": "T", "agent_id": "agent-xyz"})
        assert isinstance(run_id, str) and run_id
        await asyncio.sleep(0.05)

        MockBS.return_value.ingest_cost_event.assert_not_called()
