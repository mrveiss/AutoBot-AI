# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SLM client's role-owner and node-service calls: paths, credential, egress guard, redirects (#16346)."""

from __future__ import annotations

import socket
from unittest.mock import AsyncMock, MagicMock

import pytest

from autobot_shared import egress_allowlist as al
from services.slm_client import SLMClient

INTERNAL = "http://127.0.0.1:8001"


@pytest.fixture(autouse=True)
def _allowlist(monkeypatch):
    al.reset_internal_origin_state()
    monkeypatch.setattr(al, "_ssot_service_urls", lambda: [INTERNAL])
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda host, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    )
    yield
    al.reset_internal_origin_state()


def _client(base: str, payload: dict):
    """An SLMClient whose session answers *payload*; returns (client, session)."""
    response = AsyncMock()
    response.json = AsyncMock(return_value=payload)
    response.raise_for_status = MagicMock()
    response.__aenter__.return_value = response
    session = MagicMock()
    session.request.return_value = response
    client = SLMClient(slm_url=base)
    client._get_session = AsyncMock(return_value=session)
    return client, session


@pytest.mark.asyncio
async def test_role_owners_reads_the_owners_map_without_following_redirects():
    client, session = _client(INTERNAL, {"owners": {"redis": ["n1"]}, "multi_node_roles": []})
    assert await client.get_role_owners() == {"redis": ["n1"]}
    method, url = session.request.call_args.args
    assert (method, url.endswith("/api/roles/owners")) == ("GET", True)
    assert session.request.call_args.kwargs["allow_redirects"] is False


@pytest.mark.asyncio
async def test_node_services_and_actions_name_the_node_and_service_in_the_path():
    client, session = _client(INTERNAL, {"services": []})
    await client.list_node_services("04-Databases", search="redis-stack-server", per_page=1)
    assert session.request.call_args.args[1].endswith("/api/nodes/04-Databases/services")
    assert session.request.call_args.kwargs["params"] == {"per_page": "1", "search": "redis-stack-server"}
    await client.node_service_action("04-Databases", "redis-stack-server", "restart")
    assert session.request.call_args.args[:1] == ("POST",)
    assert session.request.call_args.args[1].endswith("/api/nodes/04-Databases/services/redis-stack-server/restart")


@pytest.mark.asyncio
async def test_a_path_segment_cannot_climb_out_of_its_slot():
    client, session = _client(INTERNAL, {})
    await client.node_service_action("../x", "a/b", "start")
    assert "/api/nodes/..%2Fx/services/a%2Fb/start" in session.request.call_args.args[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("base", ["http://10.1.2.3:8001", "http://169.254.169.254"])
async def test_a_private_non_allowlisted_origin_sends_no_request(base):
    client, session = _client(base, {"owners": {}})
    with pytest.raises(Exception):
        await client.get_role_owners()
    session.request.assert_not_called()
