# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A failed agent/peer search answers a fixed 500 and logs the cause (#21396).

Both handlers used to return ``"... failed: <exception text>"``; driver and
vector-store messages belong in the server log only.
"""

import logging
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from llc.api import agent_api, companies

_COMPANY_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_LEAK_MARKER = "LEAK-MARKER-chroma-host-9c1d"


def _request() -> MagicMock:
    req = MagicMock()
    req.state.agent_id = "agent-1"
    req.state.company_id = str(_COMPANY_ID)
    return req


def _ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = str(_COMPANY_ID)
    ctx.is_platform_admin = False
    return ctx


@pytest.mark.asyncio
async def test_peer_search_failure_returns_fixed_detail(caplog):  # noqa: ANN001
    boom = RuntimeError(f"vector store down {_LEAK_MARKER}")
    with caplog.at_level(logging.ERROR, logger=agent_api.logger.name):
        with patch.object(agent_api, "fetch_peer_rows", new=AsyncMock(side_effect=boom)):
            with pytest.raises(HTTPException) as caught:
                await agent_api.search_peer_agents(q="devops", request=_request())

    assert caught.value.status_code == 500
    assert caught.value.detail == "Peer search failed"
    assert _LEAK_MARKER not in str(caught.value.detail)
    assert "RuntimeError" not in str(caught.value.detail)
    assert any("RuntimeError" in r.getMessage() for r in caplog.records if r.levelno == logging.ERROR)


@pytest.mark.asyncio
async def test_agent_search_failure_returns_fixed_detail(caplog):  # noqa: ANN001
    boom = RuntimeError(f"vector store down {_LEAK_MARKER}")
    with caplog.at_level(logging.ERROR, logger=companies.logger.name):
        with patch("knowledge.get_knowledge_base", new=AsyncMock(side_effect=boom)):
            with pytest.raises(HTTPException) as caught:
                await companies.search_agents(
                    company_id=_COMPANY_ID,
                    q="devops",
                    limit=10,
                    _current_user={"id": "user-1"},
                    ctx=_ctx(),
                )

    assert caught.value.status_code == 500
    assert caught.value.detail == "Agent search failed"
    assert _LEAK_MARKER not in str(caught.value.detail)
    assert "RuntimeError" not in str(caught.value.detail)
    assert any("RuntimeError" in r.getMessage() for r in caplog.records if r.levelno == logging.ERROR)
