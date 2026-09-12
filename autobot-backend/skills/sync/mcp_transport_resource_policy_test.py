# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for StdioTransport's resource_policy/preexec_fn wiring (#3229, #11542).

Split out of mcp_transport_test.py to stay under the 600-line cap.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.mcp_isolation_config import BridgePolicy, IsolationMode
from skills.sync.mcp_client import MCPClient
from skills.sync.mcp_transport import StdioTransport, create_transport


def _policy(**overrides) -> BridgePolicy:
    base = dict(bridge="s1", mode=IsolationMode.SUBPROCESS, cpu_seconds=30, memory_mb=512, nofile=256, restart_max=5)
    base.update(overrides)
    return BridgePolicy(**base)


@pytest.fixture
def anyio_backend():
    """Use asyncio backend only (not trio)."""
    return "asyncio"


class TestCreateTransportThreadsResourcePolicy:
    def test_stdio_transport_receives_resource_policy(self):
        policy = _policy()
        t = create_transport("stdio://npx -y pkg", resource_policy=policy)
        assert t._resource_policy is policy

    def test_default_is_none(self):
        t = create_transport("stdio://npx -y pkg")
        assert t._resource_policy is None

    def test_remote_transport_ignores_resource_policy(self):
        """resource_policy has no effect on a transport with no subprocess."""
        t = create_transport("http://example.com/mcp", resource_policy=_policy())
        assert not hasattr(t, "_resource_policy")


class TestMCPClientThreadsResourcePolicy:
    def test_mcp_client_passes_resource_policy_to_transport(self):
        policy = _policy()
        client = MCPClient("stdio://npx -y pkg", resource_policy=policy)
        assert client._transport._resource_policy is policy


class TestStdioTransportPreexecFn:
    def test_no_policy_means_no_preexec_fn(self):
        transport = StdioTransport("npx -y pkg")
        assert transport._make_preexec_fn() is None

    def test_policy_produces_a_callable(self):
        transport = StdioTransport("npx -y pkg", resource_policy=_policy())
        preexec = transport._make_preexec_fn()
        assert callable(preexec)

    def test_preexec_fn_applies_the_policy_limits(self):
        policy = _policy(cpu_seconds=10, memory_mb=128, nofile=64)
        transport = StdioTransport("npx -y pkg", resource_policy=policy)
        preexec = transport._make_preexec_fn()

        with patch("services.mcp_isolation_config.apply_rlimits") as mock_apply:
            preexec()

        mock_apply.assert_called_once_with(cpu_seconds=10, memory_mb=128, nofile=64)

    @pytest.mark.anyio
    async def test_connect_passes_preexec_fn_to_subprocess_exec(self):
        policy = _policy()
        transport = StdioTransport("npx -y pkg", resource_policy=policy)

        mock_proc = AsyncMock()
        mock_proc.pid = 123
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)) as mock_exec:
            await transport.connect()

        assert mock_exec.call_args.kwargs["preexec_fn"] is not None

    @pytest.mark.anyio
    async def test_connect_without_policy_passes_none_preexec_fn(self):
        transport = StdioTransport("npx -y pkg")

        mock_proc = AsyncMock()
        mock_proc.pid = 123
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)) as mock_exec:
            await transport.connect()

        assert mock_exec.call_args.kwargs["preexec_fn"] is None
