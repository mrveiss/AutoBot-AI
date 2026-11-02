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


def _session(status=None, error=None):
    response = MagicMock(status=status)
    post = MagicMock(
        __aenter__=AsyncMock(return_value=response, side_effect=error), __aexit__=AsyncMock(return_value=False)
    )
    session = MagicMock(post=MagicMock(return_value=post))
    return MagicMock(__aenter__=AsyncMock(return_value=session), __aexit__=AsyncMock(return_value=False)), session


async def _run(status=None, error=None):
    factory, session = _session(status, error)
    with (
        patch.object(client, "assert_egress_policy", AsyncMock()),
        patch.object(client.aiohttp, "ClientSession", return_value=factory),
    ):
        return await client.run_compose_service_action(_NODE, "redis", "restart"), session


@pytest.mark.asyncio
async def test_the_action_goes_to_the_nodes_container() -> None:
    (ok, _), session = await _run(status=200)
    assert ok is True
    assert session.post.call_args.args[0].endswith("/containers/autobot-redis/restart")


@pytest.mark.asyncio
async def test_a_refusal_is_a_failure_that_says_so() -> None:
    (ok, message), _ = await _run(status=403)
    assert ok is False and "403" in message


@pytest.mark.asyncio
async def test_an_unreachable_proxy_is_a_failure_not_an_exception() -> None:
    (ok, message), _ = await _run(error=OSError("no route"))
    assert ok is False and "could not be reached" in message
