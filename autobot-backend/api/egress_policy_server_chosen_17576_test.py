# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Server-chosen outbound calls in ``api/`` run under ``EGRESS_POLICY`` (#17576, AC4 slice 2).

Each converted call site is driven through its real function with a real ``HTTPClientManager``
(session mocked, no network). Three host-shaped properties per site: an internal SSOT origin works on a
single-host loopback install, a public URL is allowed, and a private non-allowlisted origin is refused
before any request is sent.
"""

from __future__ import annotations

import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from api import (
    analytics,
    analytics_reporting,
    mcp_registry,
    monitoring,
    npu_workers,
    playwright,
    service_monitor,
    vnc_mcp,
    vnc_proxy,
)
from autobot_shared import egress_allowlist as al
from autobot_shared.http_client_manager import HTTPClientManager
from autobot_shared.http_egress_guard import EgressBlockedError

INTERNAL = "http://127.0.0.1:8001"
PUBLIC = "https://api.example.test:8001"
PRIVATE = "http://10.1.2.3:8001"
PUBLIC_IP = "93.184.216.34"


@pytest.fixture(autouse=True)
def _clean_allowlist():
    al.reset_internal_origin_state()
    yield
    al.reset_internal_origin_state()


@pytest.fixture
def net(monkeypatch):
    """Real manager, mocked session, a single-host loopback allowlist and mocked DNS."""
    resp = MagicMock(status=200)
    resp.json = AsyncMock(return_value=[])
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.request = AsyncMock(return_value=resp)
    mgr = HTTPClientManager()
    # On the CLASS, not the instance (#19527): HTTPClientManager() is the process
    # singleton, and undoing an instance setattr leaves the old bound method in its
    # __dict__, where it shadows every later class-level patch in the same worker.
    monkeypatch.setattr(HTTPClientManager, "get_session", AsyncMock(return_value=session))
    for attr in ("_active_requests", "_request_count", "_error_count"):
        monkeypatch.setattr(mgr, attr, getattr(mgr, attr))
    monkeypatch.setattr(al, "_ssot_service_urls", lambda: [INTERNAL])
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda host, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_IP, 0))]
    )
    for module in (analytics_reporting, mcp_registry, monitoring, playwright, service_monitor, vnc_mcp, vnc_proxy):
        monkeypatch.setattr(module, "get_http_client", lambda: mgr)
    return SimpleNamespace(session=session, monkeypatch=monkeypatch)


async def _playwright(n, base):
    n.monkeypatch.setattr(playwright, "BROWSER_VM_URL", base)
    await playwright.get_worker_status()


async def _mcp_registry(n, base):
    await mcp_registry._fetch_tools_from_bridge(base, "/api/x/tools")


async def _analytics_reporting(n, base):
    n.monkeypatch.setattr(analytics_reporting, "config", SimpleNamespace(backend_url=base))
    await analytics_reporting.fetch_quality_health()


async def _vnc_mcp(n, base):
    cfg = SimpleNamespace(backend_url=base, browser_service_url=base)
    n.monkeypatch.setattr(vnc_mcp, "config", cfg)
    await vnc_mcp.get_browser_vnc_context_mcp()


async def _vnc_proxy(n, base):
    n.monkeypatch.setattr(vnc_proxy, "config", SimpleNamespace(backend_url=base))
    await vnc_proxy.record_observation("desktop", "click", {})


async def _vnc_proxy_status(n, base):
    n.monkeypatch.setattr(vnc_proxy, "VNC_ENDPOINTS", {"desktop": base})
    await vnc_proxy.get_vnc_status("desktop", current_user={})


async def _vnc_proxy_client(n, base):
    n.monkeypatch.setattr(vnc_proxy, "VNC_ENDPOINTS", {"desktop": base})
    await vnc_proxy.get_vnc_client("desktop", current_user={})


async def _vnc_proxy_assets(n, base):
    n.monkeypatch.setattr(vnc_proxy, "VNC_ENDPOINTS", {"desktop": base})
    await vnc_proxy.proxy_vnc_assets("desktop", "app.js", current_user={})


async def _alertmanager(n, base):
    n.monkeypatch.setattr(monitoring, "ServiceURLs", SimpleNamespace(ALERTMANAGER_API=base))
    n.monkeypatch.setitem(monitoring._alertmanager_cache, "timestamp", 0)
    await monitoring._fetch_alertmanager_alerts()


async def _analytics_health(n, base):
    client = MagicMock()
    client.get = AsyncMock(return_value=MagicMock(status_code=200))
    n.session.request = client.get
    await analytics._check_service(client, "frontend", base)


async def _service_monitor(n, base):
    await service_monitor._check_http_health(f"{base}/health")


async def _npu_health(n, base):
    fake = SimpleNamespace(npu_worker_url=base)
    n.monkeypatch.setattr("autobot_shared.ssot_config.config", fake)
    resp = MagicMock(status_code=200)
    resp.json = MagicMock(return_value={"status": "ok"})
    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    n.monkeypatch.setattr(npu_workers.httpx, "AsyncClient", MagicMock(return_value=ctx))
    n.session.request = client.get  # one counter for "a request left this process"
    await npu_workers.proxy_npu_health()


SITES = [
    pytest.param(_playwright, id="playwright"),
    pytest.param(_mcp_registry, id="mcp_registry"),
    pytest.param(_analytics_reporting, id="analytics_reporting"),
    pytest.param(_vnc_mcp, id="vnc_mcp"),
    pytest.param(_vnc_proxy, id="vnc_proxy"),
    pytest.param(_service_monitor, id="service_monitor"),
    pytest.param(_vnc_proxy_status, id="vnc_proxy_status"),
    pytest.param(_vnc_proxy_client, id="vnc_proxy_client"),
    pytest.param(_vnc_proxy_assets, id="vnc_proxy_assets"),
    pytest.param(_alertmanager, id="monitoring_alertmanager"),
    pytest.param(_analytics_health, id="analytics_health"),
    pytest.param(_npu_health, id="npu_workers_health"),
]


async def _drive(site, n, base):
    """Run *site*; a refusal that the endpoint surfaces is fine, anything else is not."""
    try:
        await site(n, base)
    except (EgressBlockedError, HTTPException):
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize("site", SITES)
@pytest.mark.parametrize("base", [INTERNAL, PUBLIC], ids=["internal_ssot_origin", "public_url"])
async def test_allowed_origin_reaches_the_network(site, net, base):
    await _drive(site, net, base)
    net.session.request.assert_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("site", SITES)
async def test_private_non_allowlisted_origin_is_refused_before_any_request(site, net):
    await _drive(site, net, PRIVATE)
    net.session.request.assert_not_awaited()


@pytest.mark.asyncio
async def test_refusal_is_an_egress_blocked_error_not_a_swallowed_other_failure(net):
    with pytest.raises(EgressBlockedError):
        await mcp_registry._fetch_tools_from_bridge(PRIVATE, "/api/x/tools")


@pytest.mark.asyncio
async def test_service_monitor_reports_a_refused_target_offline(net):
    status, _ = await service_monitor._check_http_health(f"{PRIVATE}/health")
    assert status == "offline"


def test_benchmark_base_url_is_the_ssot_backend_origin():
    from api import api_benchmarks
    from autobot_shared.ssot_config import config

    assert api_benchmarks.BASE_URL == config.backend_url
    assert al.normalize_origin(api_benchmarks.BASE_URL) in al.static_internal_origins()
