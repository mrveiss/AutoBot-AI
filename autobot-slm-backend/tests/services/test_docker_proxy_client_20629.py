# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20629: a compose node's service actions go to the proxy, and a failure says so."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "_docker_proxy_client", Path(__file__).parents[2] / "services" / "docker_proxy_client.py"
)
client = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(client)

_NODE = SimpleNamespace(node_id="autobot-redis")


def _http(status=None, error=None):
    response = MagicMock(status=status)
    request = MagicMock(
        __aenter__=AsyncMock(return_value=response, side_effect=error), __aexit__=AsyncMock(return_value=False)
    )
    return MagicMock(tracked_request=MagicMock(return_value=request))


async def _run(status=None, error=None):
    http = _http(status, error)
    with (
        patch.object(client, "assert_egress_policy", AsyncMock()),
        patch.object(client, "get_http_client", return_value=http),
    ):
        return await client.run_compose_service_action(_NODE, "redis", "restart"), http


def test_a_native_slms_own_node_isnt_a_compose_node() -> None:
    fleet = MagicMock(_compose_nodes_enabled=lambda: False, _COMPOSE_NODE_SPECS=[{"id": "autobot-redis"}])
    with patch.dict("sys.modules", {"services.compose_fleet": fleet}):
        assert client.is_compose_node(_NODE) is False
    fleet._compose_nodes_enabled = lambda: True
    with patch.dict("sys.modules", {"services.compose_fleet": fleet}):
        assert client.is_compose_node(_NODE) is True
        assert client.is_compose_node(SimpleNamespace(node_id="00-SLM-Manager")) is False


@pytest.mark.asyncio
async def test_the_real_egress_guard_allows_the_configured_proxy(monkeypatch) -> None:
    """The guard isn't patched here: a private name must pass only because it is registered."""
    from autobot_shared import egress_allowlist as allowlist
    from autobot_shared.http_egress_guard import EgressBlockedError, assert_egress_policy

    monkeypatch.setenv("AUTOBOT_DOCKER_PROXY_URL", "http://autobot-docker-proxy:2375")
    allowlist.register_internal_origin_provider(client._proxy_origin)
    await assert_egress_policy("http://autobot-docker-proxy:2375/containers/autobot-redis/restart")
    with pytest.raises(EgressBlockedError):  # a control: another private address is still refused
        await assert_egress_policy("http://10.0.0.5:2375/containers/autobot-redis/restart")
    monkeypatch.delenv("AUTOBOT_DOCKER_PROXY_URL")
    allowlist._cache = None


@pytest.mark.asyncio
async def test_the_action_goes_to_the_nodes_container() -> None:
    (ok, _), http = await _run(status=200)
    assert ok is True
    method, url = http.tracked_request.call_args.args
    assert method == "POST" and url.endswith("/containers/autobot-redis/restart")
    assert http.tracked_request.call_args.kwargs["allow_redirects"] is False


@pytest.mark.asyncio
async def test_a_refusal_is_a_failure_that_says_so() -> None:
    (ok, message), _ = await _run(status=403)
    assert ok is False and "403" in message


@pytest.mark.asyncio
async def test_docker_not_answering_says_what_to_check() -> None:
    (ok, message), _ = await _run(status=503)
    assert ok is False and "Check that Docker is running" in message


@pytest.mark.asyncio
async def test_an_unreachable_proxy_is_a_failure_not_an_exception() -> None:
    (ok, message), _ = await _run(error=OSError("no route"))
    assert ok is False and "could not be reached" in message
