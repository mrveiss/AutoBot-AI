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


NODES_PATH = reg.NODES_PATH


def _nodes(*pairs):
    """An SLM /api/nodes body: (node_id, roles) pairs."""
    return {"nodes": [{"node_id": n, "roles": r} for n, r in pairs], "total": len(pairs)}


class _FakeRedis:
    def __init__(self, store):
        self.store = store

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value):
        self.store[key] = value.encode("utf-8")

    async def delete(self, key):
        self.store.pop(key, None)


@pytest.fixture(autouse=True)
def _shared_pin(monkeypatch):
    """One Redis shared by every simulated worker (#22144); never the real one."""
    store: dict = {}

    async def client():
        return _FakeRedis(store)

    monkeypatch.setattr(reg, "_pin_client", client)
    return store


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
            ("GET", NODES_PATH): _nodes(("n-b", ["browser"]), ("n-d", ["llm", "vnc"])),
            ("GET", reg.NODE_CREDENTIALS_PATH.format(node_id="n-d")): {
                "credentials": [{"credential_id": "c-d", "vnc_port": 5903}]
            },
        }
    )
    monkeypatch.setattr(reg, "_request", request)
    ep = await reg.desktop_vnc_endpoint()
    assert ep == reg.DesktopVmEndpoint("n-d", "c-d", "203.0.113.3", 6090, 5903)
    await reg.desktop_vnc_endpoint()
    assert len(calls) == 3  # endpoints, node roles and the credential; the second call is served from the TTL cache


@pytest.mark.asyncio
async def test_no_desktop_node_registered_is_none(monkeypatch):
    request, _ = _fake(
        {
            ("GET", reg.ENDPOINTS_PATH): {"endpoints": [ENDPOINTS["endpoints"][0]]},
            ("GET", NODES_PATH): _nodes(("n-b", ["vnc"])),
        }
    )
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
    both = frozenset({"n-1", "n-2"})
    assert reg._pick_desktop(twins, both)["node_id"] == "n-1"
    assert reg._pick_desktop(list(reversed(twins)), both)["node_id"] == "n-1"


def test_an_endpoint_on_a_node_without_the_vnc_role_is_ignored():
    """The live install's only credential sat on a node that is not the desktop: it must never be used."""
    stale = {"vnc_type": "desktop", "hostname": "main", "node_id": "n-main", "is_active": True}
    assert reg._pick_desktop([stale], frozenset({"n-real"})) is None
    assert reg._pick_desktop([stale], frozenset()) is None


def test_an_endpoint_on_a_vnc_node_is_picked_over_a_stale_one():
    stale = {"vnc_type": "desktop", "hostname": "a-main", "node_id": "n-main", "is_active": True}
    real = {"vnc_type": "desktop", "hostname": "z-desk", "node_id": "n-desk", "is_active": True}
    assert reg._pick_desktop([stale, real], frozenset({"n-desk"}))["node_id"] == "n-desk"


@pytest.mark.asyncio
async def test_only_a_stale_credential_on_a_non_vnc_node_means_no_desktop_vm(monkeypatch):
    """No node with the vnc role has a credential yet: desktop_vm_unavailable, not the main node's credential."""
    stale = {
        "credential_id": "c-m",
        "node_id": "n-main",
        "hostname": "main",
        "ip_address": "203.0.113.1",
        "vnc_type": "desktop",
        "port": 6080,
        "is_active": True,
    }
    request, calls = _fake(
        {
            ("GET", reg.ENDPOINTS_PATH): {"endpoints": [stale]},
            ("GET", NODES_PATH): _nodes(("n-main", ["backend", "frontend"]), ("n-real", ["llm", "vnc"])),
        }
    )
    monkeypatch.setattr(reg, "_request", request)
    assert await reg.desktop_vnc_endpoint() is None
    assert not any(c[0] != "GET" for c in calls)  # nothing stored is modified or deactivated


@pytest.mark.asyncio
async def test_node_roles_are_paged_and_cached_with_the_endpoint(monkeypatch):
    pages = {
        "1": {"nodes": [{"node_id": "n-a", "roles": ["llm"]}], "total": 2},
        "2": {"nodes": [{"node_id": "n-d", "roles": ["vnc"]}], "total": 2},
    }
    seen = []

    async def request(method, path, params=None):
        seen.append((path, (params or {}).get("page")))
        if path == reg.ENDPOINTS_PATH:
            return ENDPOINTS
        if path == NODES_PATH:
            return pages[params["page"]]
        return {"credentials": [{"credential_id": "c-d", "vnc_port": 5903}]}

    monkeypatch.setattr(reg, "_request", request)
    ep = await reg.desktop_vnc_endpoint()
    assert ep.node_id == "n-d"
    assert [p for path, p in seen if path == NODES_PATH] == ["1", "2"]
    await reg.desktop_vnc_endpoint()
    assert len([1 for path, _ in seen if path == NODES_PATH]) == 2  # cached with the endpoint


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


def test_a_second_registration_never_moves_the_pinned_desktop():
    """The viewer and its later controls must resolve one node: a new node sorting first does not take over."""
    two = [
        {"node_id": "n-a", "hostname": "a", "vnc_type": "desktop"},
        {"node_id": "n-z", "hostname": "z", "vnc_type": "desktop"},
    ]
    ids = frozenset({"n-a", "n-z"})
    assert reg._pick_desktop(two, ids)["node_id"] == "n-a"
    assert reg._pick_desktop(two, ids, pinned="n-z")["node_id"] == "n-z"
    assert reg._pick_desktop(two, frozenset({"n-a"}), pinned="n-z")["node_id"] == "n-a"  # lost its role: released


@pytest.mark.asyncio
async def test_the_registered_desktop_origin_passes_the_egress_policy_and_others_do_not(monkeypatch):
    from autobot_shared.egress_allowlist import is_internal_origin

    request, _ = _fake(
        {
            ("GET", reg.ENDPOINTS_PATH): ENDPOINTS,
            ("GET", NODES_PATH): _nodes(("n-d", ["vnc"])),
            ("GET", reg.NODE_CREDENTIALS_PATH.format(node_id="n-d")): {"credentials": []},
        }
    )
    monkeypatch.setattr(reg, "_request", request)
    assert not await is_internal_origin("https://203.0.113.3:6090/websockify")  # not registered yet
    await reg.desktop_vnc_endpoint()
    assert await is_internal_origin("https://203.0.113.3:6090/vnc.html")
    assert await is_internal_origin("wss://203.0.113.3:6090/websockify")
    assert not await is_internal_origin("https://203.0.113.3:6091/vnc.html")  # another port
    assert not await is_internal_origin("https://203.0.113.9:6090/vnc.html")  # another host


def test_registry_calls_carry_the_internal_service_key_only_when_configured(monkeypatch):
    monkeypatch.setattr(reg.node_proxy, "internal_api_key", lambda: "k")
    assert reg._registry_headers() == {"X-Internal-API-Key": "k"}
    monkeypatch.setattr(reg.node_proxy, "internal_api_key", lambda: "")
    assert reg._registry_headers() == {}


@pytest.mark.asyncio
async def test_a_second_worker_keeps_the_pin_the_first_worker_stored(_shared_pin):
    """Worker B has no process pin of its own, yet keeps the node worker A chose (#22144)."""
    await reg._store_pin("n-z")
    reg._pinned_node_id = None  # worker B: fresh process, same Redis
    assert await reg._load_pin() == "n-z"
    assert _shared_pin[reg.PIN_REDIS_KEY] == b"n-z"
    await reg._store_pin(None)
    assert await reg._load_pin() is None


@pytest.mark.asyncio
async def test_redis_down_falls_back_to_this_workers_pin(monkeypatch):
    async def broken():
        raise ConnectionError("down")

    monkeypatch.setattr(reg, "_pin_client", broken)
    await reg._store_pin("n-a")
    assert await reg._load_pin() == "n-a"
