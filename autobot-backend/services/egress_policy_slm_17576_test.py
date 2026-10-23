# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SLM websocket handshake redirects and the SLM policy read are guarded (#17576, AC4 slice 4).

``websockets`` 15.x follows a 3xx handshake response (``Location``) to another host, so a check of the first
URL alone is not enough: ``connect_no_redirect`` surfaces the redirect instead. A loopback test server
redirects to a second one; the control proves the plain client follows it and the guarded one does not.
``fetch_slm_policy_json`` asserts ``EGRESS_POLICY`` on the SLM URL and refuses redirects (network mocked).
"""

from __future__ import annotations

import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from websockets.exceptions import InvalidStatus

from autobot_shared import egress_allowlist as al
from autobot_shared.ws_no_redirect import connect_no_redirect
from llc.services.slm_policy import fetch_slm_policy_json

INTERNAL = "http://127.0.0.1:8001"


@pytest.fixture(autouse=True)
def _clean_allowlist(monkeypatch):
    al.reset_internal_origin_state()
    monkeypatch.setattr(al, "_ssot_service_urls", lambda: [INTERNAL])
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda host, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    )
    yield
    al.reset_internal_origin_state()


async def _redirecting_pair():
    """(redirector, target, hits): connecting to the redirector 302s to the target; hits counts target upgrades."""
    hits = []

    async def to_target(connection, request):
        hits.append(request.path)

    async def handler(ws):
        await ws.close()

    target = await serve(handler, "127.0.0.1", 0, process_request=to_target)
    target_url = "ws://127.0.0.1:%d/hop" % target.sockets[0].getsockname()[1]

    async def redirect(connection, request):
        return connection.respond(302, "moved")

    async def redirect_with_location(connection, request):
        response = await redirect(connection, request)
        response.headers["Location"] = target_url
        return response

    redirector = await serve(handler, "127.0.0.1", 0, process_request=redirect_with_location)
    return redirector, target, hits


@pytest.mark.asyncio
async def test_plain_websockets_client_follows_a_handshake_redirect_control():
    redirector, target, hits = await _redirecting_pair()
    try:
        async with connect("ws://127.0.0.1:%d/" % redirector.sockets[0].getsockname()[1]):
            pass
        assert hits == ["/hop"]  # the instrument works: an unguarded client reached the redirect target
    finally:
        redirector.close()
        target.close()


@pytest.mark.asyncio
async def test_connect_no_redirect_surfaces_the_redirect_and_never_reaches_the_target():
    redirector, target, hits = await _redirecting_pair()
    try:
        with pytest.raises(InvalidStatus) as caught:
            async with connect_no_redirect("ws://127.0.0.1:%d/" % redirector.sockets[0].getsockname()[1]):
                pass
        assert caught.value.response.status_code == 302
        assert hits == []
    finally:
        redirector.close()
        target.close()


def _slm_client(url):
    response = AsyncMock(status=200)
    response.json = AsyncMock(return_value={"value": '{"enabled": true}'})
    response.__aenter__.return_value = response
    session = MagicMock()
    session.get.return_value = response
    client = MagicMock()
    client._get_session = AsyncMock(return_value=session)
    client._rest_url = MagicMock(return_value=url)
    return client, session


@pytest.mark.asyncio
async def test_policy_read_from_the_allowlisted_slm_origin_proceeds_without_following_redirects():
    client, session = _slm_client(INTERNAL + "/api/settings/k")
    with patch("llc.services.slm_policy.get_slm_client", return_value=client):
        assert await fetch_slm_policy_json("k") == {"enabled": True}
    assert session.get.call_args.kwargs["allow_redirects"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["http://10.1.2.3:8001/api/settings/k", "http://169.254.169.254/api/settings/k"])
async def test_policy_read_from_a_private_non_allowlisted_origin_sends_no_request(url):
    client, session = _slm_client(url)
    with patch("llc.services.slm_policy.get_slm_client", return_value=client):
        assert await fetch_slm_policy_json("k") is None
    session.get.assert_not_called()
