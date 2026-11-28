# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""REST calls to the SLM carry the same credential the WebSocket uses when no static token is set (#20943)."""

import logging
from unittest.mock import patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from autobot_shared.auth.jwt_core import decode_jwt
from services.slm_client import SLMClient

pytestmark = pytest.mark.usefixtures("slm_egress_open")  # subject is the credential, not egress

_SECRET = "unit-test-signing-secret-0123456789abcdef"  # pragma: allowlist secret
_SIGNER_PATH = "services.slm_client._get_slm_signing_secret"


def _auth_required_app() -> web.Application:
    """An SLM stand-in that answers 401 unless the bearer verifies against the shared secret."""

    async def agents(request: web.Request) -> web.Response:
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer ") or decode_jwt(header[7:], secret=_SECRET) is None:
            return web.Response(status=401)
        return web.json_response(
            {"agents": [{"agent_id": "agent-a", "llm_provider": "ollama", "llm_model": "m", "is_default": True}]}
        )

    app = web.Application()
    app.router.add_get("/api/agents", agents)
    return app


@pytest.mark.asyncio
async def test_rest_session_mints_service_jwt_without_static_token(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    client = SLMClient(slm_url="http://slm.invalid:8000")
    with patch(_SIGNER_PATH, return_value=_SECRET):
        session = await client._get_session()
    header = session.headers["Authorization"]
    assert header.startswith("Bearer ")
    claims = decode_jwt(header[7:], secret=_SECRET)
    assert claims["sub"] == "service:backend" and claims["service"] is True
    assert _SECRET not in caplog.text and header[7:] not in caplog.text
    await client.disconnect()


@pytest.mark.asyncio
async def test_static_token_wins_and_nothing_is_minted() -> None:
    client = SLMClient(slm_url="http://slm.invalid:8000", auth_token="static-operator-token")
    with patch(_SIGNER_PATH, return_value=_SECRET) as secret, patch("services.slm_client._mint_service_jwt") as mint:
        session = await client._get_session()
    assert session.headers["Authorization"] == "Bearer static-operator-token"
    mint.assert_not_called()
    secret.assert_not_called()
    await client.disconnect()


@pytest.mark.asyncio
async def test_no_token_and_no_secret_sends_no_authorization() -> None:
    client = SLMClient(slm_url="http://slm.invalid:8000")
    with patch(_SIGNER_PATH, return_value=None):
        session = await client._get_session()
    assert "Authorization" not in session.headers
    await client.disconnect()


@pytest.mark.asyncio
async def test_token_is_reminted_on_each_session_use() -> None:
    """A reused session never keeps an expired minted token: the bearer is re-resolved per call."""
    client = SLMClient(slm_url="http://slm.invalid:8000")
    with (
        patch(_SIGNER_PATH, return_value=_SECRET),
        patch("services.slm_client._mint_service_jwt", side_effect=["tok-1", "tok-2"]),
    ):
        first = (await client._get_session()).headers["Authorization"]
        second = (await client._get_session()).headers["Authorization"]
    assert (first, second) == ("Bearer tok-1", "Bearer tok-2")
    await client.disconnect()


@pytest.mark.asyncio
async def test_fetch_all_agents_succeeds_against_auth_requiring_slm_without_static_token() -> None:
    server = TestServer(_auth_required_app())
    await server.start_server()
    try:
        client = SLMClient(slm_url=str(server.make_url("")))
        with patch(_SIGNER_PATH, return_value=_SECRET):
            await client._fetch_all_agents()
        assert client.cache.get("agent-a")["llm_provider"] == "ollama"
        await client.disconnect()
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_fetch_all_agents_still_401_without_any_credential() -> None:
    """Control: the stand-in really rejects an unauthenticated call, so the 200 above is the credential's doing."""
    server = TestServer(_auth_required_app())
    await server.start_server()
    try:
        client = SLMClient(slm_url=str(server.make_url("")))
        with patch(_SIGNER_PATH, return_value=None):
            await client._fetch_all_agents()
        assert client.cache.get("agent-a") is None
        await client.disconnect()
    finally:
        await server.close()
