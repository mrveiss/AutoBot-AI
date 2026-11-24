# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The desktop VM is read from the SLM's registered VNC endpoints (#22145, owner 2026-11-24)."""

import pytest

from services import slm_vnc_registry as reg

ENDPOINTS = {
    "endpoints": [
        {
            "credential_id": "c-b",
            "node_id": "n-b",
            "hostname": "b",
            "ip_address": "203.0.113.2",
            "vnc_type": "browser",
            "port": 6081,
            "is_active": True,
        },
        {
            "credential_id": "c-x",
            "node_id": "n-x",
            "hostname": "x",
            "ip_address": "203.0.113.9",
            "vnc_type": "desktop",
            "port": 6080,
            "is_active": False,
        },
        {
            "credential_id": "c-d",
            "node_id": "n-d",
            "hostname": "d",
            "ip_address": "203.0.113.3",
            "vnc_type": "desktop",
            "port": 6090,
            "is_active": True,
        },
    ]
}


@pytest.fixture(autouse=True)
def _fresh():
    reg.reset_cache()
    yield
    reg.reset_cache()


def _fake(responses):
    calls = []

    async def request(method, path, params=None):
        calls.append((method, path, params))
        value = responses[(method, path)]
        if isinstance(value, Exception):
            raise value
        return value

    return request, calls


@pytest.mark.asyncio
async def test_picks_the_active_desktop_node_with_its_raw_vnc_port(monkeypatch):
    request, calls = _fake(
        {
            ("GET", reg.ENDPOINTS_PATH): ENDPOINTS,
            ("GET", reg.NODE_CREDENTIALS_PATH.format(node_id="n-d")): {
                "credentials": [{"credential_id": "c-d", "vnc_port": 5903}]
            },
        }
    )
    monkeypatch.setattr(reg, "_request", request)
    ep = await reg.desktop_vnc_endpoint()
    assert ep == reg.DesktopVmEndpoint("n-d", "c-d", "203.0.113.3", 6090, 5903)
    await reg.desktop_vnc_endpoint()
    assert len(calls) == 2  # the second call is served from the TTL cache


@pytest.mark.asyncio
async def test_no_desktop_node_registered_is_none(monkeypatch):
    request, _ = _fake({("GET", reg.ENDPOINTS_PATH): {"endpoints": [ENDPOINTS["endpoints"][0]]}})
    monkeypatch.setattr(reg, "_request", request)
    assert await reg.desktop_vnc_endpoint() is None


@pytest.mark.asyncio
async def test_a_failing_registry_raises_instead_of_looking_empty(monkeypatch):
    request, _ = _fake({("GET", reg.ENDPOINTS_PATH): reg.SlmRegistryUnavailable("SLM registry request failed: X")})
    monkeypatch.setattr(reg, "_request", request)
    with pytest.raises(reg.SlmRegistryUnavailable):
        await reg.desktop_vnc_endpoint()


@pytest.mark.asyncio
async def test_no_slm_link_means_no_desktop_vm(monkeypatch):
    """Decided explicitly: no SLM link is 'no registered desktop node' (entry absent), not an outage."""
    request, _ = _fake({("GET", reg.ENDPOINTS_PATH): reg.SlmLinkNotInitialised("no link")})
    monkeypatch.setattr(reg, "_request", request)
    assert await reg.desktop_vnc_endpoint() is None


@pytest.mark.asyncio
async def test_password_is_the_nodes_own_via_connect_then_exchange(monkeypatch):
    request, calls = _fake(
        {
            ("POST", reg.CONNECT_PATH.format(credential_id="c-d")): {"connection_token": "tok-1"},
            ("POST", reg.EXCHANGE_PATH): {"password": "node-pw"},  # pragma: allowlist secret
        }
    )
    monkeypatch.setattr(reg, "_request", request)
    ep = reg.DesktopVmEndpoint("n-d", "c-d", "203.0.113.3", 6090, 5903)
    assert await reg.desktop_vnc_password(ep) == b"node-pw"
    assert calls[1][2] == {"token": "tok-1"}


@pytest.mark.asyncio
async def test_no_token_means_no_password(monkeypatch):
    request, _ = _fake({("POST", reg.CONNECT_PATH.format(credential_id="c-d")): {}})
    monkeypatch.setattr(reg, "_request", request)
    assert await reg.desktop_vnc_password(reg.DesktopVmEndpoint("n-d", "c-d", "h", 1, None)) is None


def test_the_pick_is_stable_on_hostname_then_node_id():
    twins = [
        {"vnc_type": "desktop", "hostname": "same", "node_id": "n-2", "is_active": True},
        {"vnc_type": "desktop", "hostname": "same", "node_id": "n-1", "is_active": True},
    ]
    assert reg._pick_desktop(twins)["node_id"] == "n-1"
    assert reg._pick_desktop(list(reversed(twins)))["node_id"] == "n-1"


@pytest.mark.asyncio
async def test_concurrent_callers_share_one_registry_read(monkeypatch):
    import asyncio

    reads = []

    async def slow_fetch():
        reads.append(1)
        await asyncio.sleep(0.01)
        return reg.DesktopVmEndpoint("n", "c", "203.0.113.5", 6090, 5901)

    monkeypatch.setattr(reg, "_fetch_endpoint", slow_fetch)
    results = await asyncio.gather(*(reg.desktop_vnc_endpoint() for _ in range(5)))
    assert len(reads) == 1 and all(r.host == "203.0.113.5" for r in results)
