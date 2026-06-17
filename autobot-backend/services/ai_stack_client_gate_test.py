# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for the AI Stack client enabled-gate (#9782).

When disabled, the client must NOT attempt any network connection (which is
what produced the ~237 per-boot "AI Stack client error" warnings in compose /
single_user deployments that ship no AI Stack VM).
"""

import pytest

from autobot_shared.status_enums import ConnectionStatus
from services.ai_stack_client import AIStackClient


@pytest.mark.asyncio
async def test_health_check_disabled_returns_disabled_without_network(monkeypatch):
    client = AIStackClient(enabled=False)

    # Fail loudly if any HTTP request is attempted while disabled.
    def _boom(*_a, **_k):
        raise AssertionError("disabled client must not make network requests")

    monkeypatch.setattr(client, "_make_request", _boom)

    result = await client.health_check()
    assert result["status"] == "disabled"
    assert client.connection_status is ConnectionStatus.DISABLED
    assert client.connection_status == "disabled"  # str-subclass back-compat


@pytest.mark.asyncio
async def test_connect_disabled_is_quiet_noop():
    client = AIStackClient(enabled=False)
    await client.connect()  # must not raise / must not hit the network
    assert client.connection_status is ConnectionStatus.DISABLED


def test_start_retry_loop_noop_when_disabled():
    client = AIStackClient(enabled=False)
    client.start_retry_loop()
    assert client._retry_task is None


def test_enabled_defaults_to_true_when_unspecified():
    # Preserves existing behavior for real deployments (default-on).
    client = AIStackClient(enabled=True)
    assert client.enabled is True
