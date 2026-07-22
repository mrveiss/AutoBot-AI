# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Canonical SLM-settings JSON policy reader (#11359)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.services.slm_policy import fetch_slm_policy_json


@pytest.mark.asyncio
async def test_none_when_no_slm_client():
    with patch("llc.services.slm_policy.get_slm_client", return_value=None):
        assert await fetch_slm_policy_json("some.key") is None


@pytest.mark.asyncio
async def test_none_on_non_200_response():
    response = AsyncMock()
    response.status = 404
    response.__aenter__.return_value = response
    session = MagicMock()
    session.get.return_value = response
    client = MagicMock()
    client._get_session = AsyncMock(return_value=session)
    client.slm_url = "http://slm"
    with patch("llc.services.slm_policy.get_slm_client", return_value=client):
        assert await fetch_slm_policy_json("some.key") is None


@pytest.mark.asyncio
async def test_parses_escaped_json_value():
    response = AsyncMock()
    response.status = 200
    response.json = AsyncMock(return_value={"value": '{"enabled": true}'})
    response.__aenter__.return_value = response
    session = MagicMock()
    session.get.return_value = response
    client = MagicMock()
    client._get_session = AsyncMock(return_value=session)
    client.slm_url = "http://slm"
    with patch("llc.services.slm_policy.get_slm_client", return_value=client):
        assert await fetch_slm_policy_json("some.key") == {"enabled": True}


@pytest.mark.asyncio
async def test_none_on_exception():
    client = MagicMock()
    client._get_session = AsyncMock(side_effect=RuntimeError("boom"))
    with patch("llc.services.slm_policy.get_slm_client", return_value=client):
        assert await fetch_slm_policy_json("some.key") is None
