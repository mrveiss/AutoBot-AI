# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/testkit/mcp_client_doubles.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""MCP client doubles that honour the discovery contract (#17467).

`services/mcp_aggregation.py` requires a client factory to expose
`discover_tools_detailed() -> ToolDiscovery`, and states that contract rather
than probing for it, because `AsyncMock` auto-creates every attribute: a probe
that cannot say no is not a probe.

The same property makes a stale double dangerous in the other direction. A
double that stubs only `discover_tools()` answers `discover_tools_detailed()`
with a fresh mock, so the caller receives a mock where a tool list belongs. The
symptom is an empty tool set and `assert 'search' in []` several layers away --
not an AttributeError naming the missing method. Building the double here means
the contract has one place to change when it changes again.
"""

from typing import Any, Iterable, Sequence
from unittest.mock import AsyncMock


def mcp_client_double(tools: Sequence[Any] = (), rejected: Iterable[Any] = ()) -> AsyncMock:
    """An async-context-manager client double advertising *tools*.

    Both discovery forms are stubbed with real values, so a caller reaching for
    either gets a list rather than a mock.
    """
    from skills.sync.mcp_client import ToolDiscovery

    accepted = list(tools)
    client = AsyncMock()
    client.discover_tools_detailed = AsyncMock(return_value=ToolDiscovery(accepted=accepted, rejected=list(rejected)))
    client.discover_tools = AsyncMock(return_value=accepted)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client
