# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`/fleet/services` is a thin delegate of `/orchestration/fleet/services` (#17856).

The two routes aggregated the same rows twice. The orchestration handler is the public path and
now the only implementation; the legacy route returns whatever it returns, so the two responses
cannot drift while the SLM frontend still calls the old path.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from testkit.fake_async_session import FakeAsyncSession

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _real_orm_import import import_modules_with_real_orm  # noqa: E402

_services_api, _orchestration_api = import_modules_with_real_orm(import_names=("api.services", "api.orchestration"))

_PRINCIPAL = {"admin": True, "role": "admin", "sub": "tester"}


def _db() -> FakeAsyncSession:
    services = [
        SimpleNamespace(service_name="redis", node_id="n1", status="running", port=6379, category="autobot"),
        SimpleNamespace(service_name="redis", node_id="n2", status="failed", port=6379, category=None),
    ]
    nodes = [
        SimpleNamespace(node_id="n1", hostname="alpha", ip_address="10.0.0.1"),
        SimpleNamespace(node_id="n2", hostname="beta", ip_address="10.0.0.2"),
    ]
    # Answers the handler's two selects in order: services, then nodes; a third raises.
    return FakeAsyncSession(results=[services, nodes], strict=True)


@pytest.mark.asyncio
async def test_legacy_route_returns_the_orchestration_response() -> None:
    legacy = await _services_api.legacy_fleet_services(_db(), _PRINCIPAL)
    public = await _orchestration_api.get_fleet_services(_db(), _PRINCIPAL)
    assert legacy.model_dump() == public.model_dump()


@pytest.mark.asyncio
async def test_node_rows_carry_address_and_port() -> None:
    """The legacy route exposed ip_address and port; the one implementation must keep them."""
    result = await _services_api.legacy_fleet_services(_db(), _PRINCIPAL)
    node = result.services[0].nodes[0]
    assert (node.hostname, node.ip_address, node.port) == ("alpha", "10.0.0.1", 6379)
    assert (result.services[0].running_count, result.services[0].failed_count) == (1, 1)
