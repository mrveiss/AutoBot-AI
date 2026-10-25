# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""EGRESS_POLICY: internal-origin allowlist, manager mode, raw-client entry point (#17576, AC4)."""

import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from autobot_shared import egress_allowlist as al
from autobot_shared import network_constants as _nc
from autobot_shared.http_client_manager import HTTPClientManager
from autobot_shared.http_egress_guard import (
    EGRESS_POLICY,
    EgressBlockedError,
    assert_egress_policy,
    assert_public_egress,
)
from autobot_shared.ssot_config import config

PUBLIC_IP = "93.184.216.34"


@pytest.fixture(autouse=True)
def _clean_state():
    al.reset_internal_origin_state()
    yield
    al.reset_internal_origin_state()


@pytest.fixture
def pinned_internal(monkeypatch):
    """A deterministic single-host layout: one internal origin on loopback."""
    monkeypatch.setattr(al, "_ssot_service_urls", lambda: ["http://127.0.0.1:8001", "http://127.0.0.1:11434"])


# --- normalisation -----------------------------------------------------------


@pytest.mark.parametrize(
    "url,expected",
    [
        ("HTTP://Example.COM/a/b?q=1", "http://example.com:80"),
        ("https://example.com", "https://example.com:443"),
        ("ws://example.com/x", "ws://example.com:80"),
        ("wss://example.com/x", "wss://example.com:443"),
        ("http://example.com:8080/x", "http://example.com:8080"),
        ("http://[::1]:8001/p", "http://[::1]:8001"),
        ("http://[2001:DB8::1]/p", "http://[2001:db8::1]:80"),
        ("http://" + "u" + ":" + "p" + "@example.com:81/", "http://example.com:81"),
    ],
)
def test_normalize_origin(url, expected):
    assert al.normalize_origin(url) == expected


@pytest.mark.parametrize(
    "url", ["example.com", "localhost:8080", "10.0.0.1:80", "", "/just/a/path", "http://", "http://a:99999", None, 5]
)
def test_normalize_origin_rejects_unusable_input(url):
    assert al.normalize_origin(url) is None


def test_build_and_match_use_the_same_normaliser(pinned_internal):
    assert al.static_internal_origins() == {"http://127.0.0.1:8001", "http://127.0.0.1:11434"}


# --- the SSOT-derived set ----------------------------------------------------


def test_ssot_set_contains_the_configured_service_origins():
    origins = al.static_internal_origins()
    for name in ("backend_url", "ollama_url", "slm_url", "aistack_url", "npu_worker_url"):
        assert al.normalize_origin(getattr(config, name)) in origins, name
    assert al.normalize_origin(f"http://{config.vm.chromadb}:{config.port.chromadb}") in origins


@pytest.mark.parametrize("name", ["chrome_cdp_url", "websocket_url", "redis_url"])
def test_non_node_to_node_origins_are_not_internal(name):
    """CDP / websocket / redis are not node-to-node HTTP targets (#17576 review)."""
    origin = al.normalize_origin(getattr(config, name))
    own = {
        al.normalize_origin(getattr(config, n)) for n in ("backend_url", "ollama_url", "aistack_url", "npu_worker_url")
    }
    if origin in own:  # single-host layouts may share an origin with a legitimate service; only distinct ones count
        pytest.skip(f"{name} shares an origin with an allowlisted service in this layout")
    assert origin not in al.static_internal_origins()


def test_cdp_and_websocket_origins_are_dropped_with_distinct_ports(monkeypatch):
    fake = SimpleNamespace(
        backend_url="http://10.0.0.1:8001",
        ollama_url="http://10.0.0.1:11434",
        aistack_url="http://10.0.0.1:8080",
        npu_worker_url="http://10.0.0.1:8081",
        tts_worker_url="http://10.0.0.1:8083",
        browser_service_url="http://10.0.0.1:3000",
        slm_url="http://10.0.0.1:8000",
        chrome_cdp_url="http://10.0.0.1:9222",
        vnc_url="http://10.0.0.1:6080/vnc.html",
        frontend_url="http://10.0.0.1:5173",
        websocket_url="ws://10.0.0.1:8001/api/ws",
        vm=SimpleNamespace(chromadb="10.0.0.1", main="10.0.0.1", browser="10.0.0.2"),
        port=SimpleNamespace(chromadb=8100, vnc=6080),
        llm=SimpleNamespace(lmstudio_host="http://10.0.0.9:1234"),
        vllm_host="http://10.0.0.9:8000",
    )
    import autobot_shared.ssot_config as ssot

    monkeypatch.setattr(ssot, "config", fake)
    monkeypatch.setattr(_nc, "ServiceURLs", _PROM)
    origins = al.static_internal_origins()
    assert (
        "http://10.0.0.1:8100" in origins and len(origins) == 8 + len(SERVER_CALLED) + 3
    )  # +3: SLM websocket, LM Studio, vLLM
    for dropped in ("http://10.0.0.1:9222", "ws://10.0.0.1:8001"):
        assert dropped not in origins
    assert set(SERVER_CALLED) <= origins
    assert "http://10.0.0.1:6080/vnc.html" not in origins  # the human link, not the origin


# --- server-called origins (#17576 slice 2): frontend, VNC, Prometheus, Alertmanager ---------------------

SERVER_CALLED = (
    "http://10.0.0.1:5173",  # config.frontend_url
    "http://10.0.0.1:6080",  # vm.main + port.vnc
    "wss://10.0.0.1:6080",  # the websockify call vnc_proxy makes
    "http://10.0.0.2:6080",  # vm.browser + port.vnc
    "wss://10.0.0.2:6080",
    "http://10.0.0.3:9093",  # ServiceURLs.ALERTMANAGER_API
)
_PROM = SimpleNamespace(PROMETHEUS_API="http://10.0.0.3:9090", ALERTMANAGER_API="http://10.0.0.3:9093")


@pytest.fixture
def server_called(monkeypatch):
    fake = SimpleNamespace(
        frontend_url="http://10.0.0.1:5173",
        slm_url="http://10.0.0.1:8000",
        vm=SimpleNamespace(main="10.0.0.1", browser="10.0.0.2"),
        port=SimpleNamespace(vnc=6080),
        llm=SimpleNamespace(lmstudio_host="http://10.0.0.9:1234"),
        vllm_host="http://10.0.0.9:8000",
    )
    import autobot_shared.ssot_config as ssot

    monkeypatch.setattr(ssot, "config", fake)
    monkeypatch.setattr(_nc, "ServiceURLs", _PROM)
    monkeypatch.setattr(al, "_ssot_service_urls", al._server_called_urls)


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", SERVER_CALLED)
async def test_server_called_origin_is_internal_exactly(server_called, origin):
    assert await al.is_internal_origin(origin + "/x")
    scheme, _, rest = origin.partition("://")
    host, _, port = rest.rpartition(":")
    assert not await al.is_internal_origin(f"{scheme}://{host}:{int(port) + 1}/x")  # same host, another port
    assert not await al.is_internal_origin(f"{scheme}://10.9.9.9:{port}/x")  # another host, same port


@pytest.mark.asyncio
async def test_chrome_cdp_and_vnc_link_stay_out(server_called):
    assert not await al.is_internal_origin("http://10.0.0.1:9222/json")
    assert not await al.is_internal_origin("ws://10.0.0.1:8001/api/ws")


def test_redis_url_is_not_an_http_origin():
    assert al.normalize_origin(config.redis_url) not in al.static_internal_origins()


# --- manager mode ------------------------------------------------------------


@pytest.fixture
def manager(monkeypatch):
    mgr = HTTPClientManager()
    session = MagicMock()
    session.request = AsyncMock(return_value="response")
    # On the CLASS, not the instance (#19527): HTTPClientManager() is the process
    # singleton, and undoing an instance setattr leaves the old bound method in its
    # __dict__, where it shadows every later class-level patch in the same worker.
    monkeypatch.setattr(HTTPClientManager, "get_session", AsyncMock(return_value=session))
    # request() hands the active-request slot to the caller; restore the counters so a shared
    # manager instance does not leak this module's in-flight count into later tests.
    for attr in ("_active_requests", "_request_count", "_error_count"):
        monkeypatch.setattr(mgr, attr, getattr(mgr, attr))
    return mgr, session


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["backend_url", "ollama_url"])
async def test_configured_internal_host_is_allowed_under_policy(manager, name):
    mgr, session = manager
    assert await mgr.request("GET", getattr(config, name) + "/health", guard_egress=EGRESS_POLICY) == "response"
    session.request.assert_awaited_once()


@pytest.mark.asyncio
async def test_loopback_internal_origin_is_allowed_though_url_safety_blocks_loopback(manager, pinned_internal):
    mgr, _ = manager
    await mgr.request("GET", "http://127.0.0.1:8001/api/x", guard_egress=EGRESS_POLICY)
    with pytest.raises(EgressBlockedError):
        await mgr.request("GET", "http://127.0.0.1:8001/api/x", guard_egress=False)


@pytest.mark.asyncio
async def test_public_url_is_allowed_with_mocked_dns(manager, monkeypatch, pinned_internal):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda host, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_IP, 0))]
    )
    mgr, session = manager
    await mgr.request("GET", "https://api.example.test/v1", guard_egress=EGRESS_POLICY)
    session.request.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["http://10.1.2.3:8001/x", "http://192.168.1.10/x"])
async def test_private_non_allowlisted_origin_is_refused(manager, pinned_internal, url):
    mgr, session = manager
    with pytest.raises(EgressBlockedError):
        await mgr.request("GET", url, guard_egress=EGRESS_POLICY)
    session.request.assert_not_awaited()


@pytest.mark.asyncio
async def test_known_internal_host_on_a_different_port_is_refused(manager, pinned_internal):
    mgr, session = manager
    with pytest.raises(EgressBlockedError):
        await mgr.request("GET", "http://127.0.0.1:9999/x", guard_egress=EGRESS_POLICY)
    session.request.assert_not_awaited()


@pytest.mark.asyncio
async def test_policy_still_refuses_redirects(manager, pinned_internal):
    mgr, _ = manager
    with pytest.raises(ValueError):
        await mgr.request("GET", "http://127.0.0.1:8001/x", guard_egress=EGRESS_POLICY, allow_redirects=True)


def test_default_stays_unguarded():
    import inspect

    assert inspect.signature(HTTPClientManager.request).parameters["guard_egress"].default is None


# --- raw-client entry point --------------------------------------------------


@pytest.mark.asyncio
async def test_assert_egress_policy_matches_manager_mode(pinned_internal, monkeypatch):
    await assert_egress_policy("http://127.0.0.1:8001/x")
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda host, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_IP, 0))]
    )
    await assert_egress_policy("https://api.example.test/v1")
    for url in ("http://10.1.2.3/x", "http://127.0.0.1:9999/x", "http://169.254.169.254/latest"):
        with pytest.raises(EgressBlockedError):
            await assert_egress_policy(url)


@pytest.mark.asyncio
async def test_assert_public_egress_refuses_an_internal_origin_that_policy_allows(pinned_internal, monkeypatch):
    await assert_egress_policy("http://127.0.0.1:8001/x")
    with pytest.raises(EgressBlockedError):
        await assert_public_egress("http://127.0.0.1:8001/x")
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda host, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_IP, 0))]
    )
    await assert_public_egress("https://api.example.test/v1")


# --- providers and the TTL cache --------------------------------------------


@pytest.mark.asyncio
async def test_provider_origins_are_allowed_and_cached_for_the_ttl(pinned_internal, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(al.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(al, "EGRESS_INTERNAL_ORIGINS_TTL_S", 30)
    provider = AsyncMock(return_value=["http://10.9.9.9:8095"])
    al.register_internal_origin_provider(provider)

    await assert_egress_policy("http://10.9.9.9:8095/x")
    await assert_egress_policy("http://10.9.9.9:8095/y")
    assert provider.await_count == 1
    clock[0] += 29
    await al.internal_origins()
    assert provider.await_count == 1
    clock[0] += 2
    await al.internal_origins()
    assert provider.await_count == 2


@pytest.mark.asyncio
async def test_slow_provider_is_abandoned_after_the_timeout(pinned_internal, monkeypatch):
    import asyncio

    async def slow():
        await asyncio.sleep(5)
        return ["http://10.9.9.9:1"]

    monkeypatch.setattr(al, "EGRESS_PROVIDER_TIMEOUT_S", 0.05)
    al.register_internal_origin_provider(slow)
    assert await al.internal_origins() == al.static_internal_origins()


@pytest.mark.asyncio
async def test_provider_exception_leaves_the_static_set_intact(pinned_internal, caplog):
    al.register_internal_origin_provider(AsyncMock(side_effect=RuntimeError("db down")))
    assert await al.internal_origins() == {"http://127.0.0.1:8001", "http://127.0.0.1:11434"}
    assert "provider" in caplog.text
    await assert_egress_policy("http://127.0.0.1:8001/x")


# --- parser differentials (#17576 review, HIGH) -----------------------------

_DIFFERENTIAL_URLS = [
    "http://169.254.169.254\\@127.0.0.1:8001/",
    "http://169.254.169.254:80\\@127.0.0.1:8001/",
    "http://127.0.0.1:8001\\@169.254.169.254/",
    "http://evil.example@127.0.0.1:8001/",
    "http://u" + ":p@127.0.0.1:8001/",
    "http://127.0.0.1:8001@169.254.169.254/",
    "http://127.0.0.1\t:8001/",
    "http://127.0.0.1:8001\n/",
    "http://127.0.0.1\r\n:8001/",
    "http://127.0.0.%31:8001/",
    "http://127.0.0.1%2e:8001/",
    "http://127.0.0.1:08001/",
    "http://127.0.0.1:8001 @169.254.169.254/",
    "http://\u2460\u2467.0.0.1:8001/",
]


@pytest.mark.parametrize("url", _DIFFERENTIAL_URLS, ids=lambda u: repr(u)[:40])
def test_ambiguous_urls_are_not_internal_and_fall_through(url, pinned_internal):
    assert al.strict_origin(url) is None


@pytest.mark.asyncio
async def test_metadata_differential_probe_is_refused_under_policy(pinned_internal):
    with pytest.raises(EgressBlockedError):
        await assert_egress_policy("http://169.254.169.254\\@127.0.0.1:8001/")


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8001/a?b=c#d",
        "HTTP://127.0.0.1:8001",
        "http://[::1]:8001/x",
        "http://localhost:8001/",
        "https://svc.internal/x",
    ],
)
def test_accepted_internal_urls_parse_identically_in_every_client_stack(url):
    import httpx
    import yarl
    from urllib3.util import parse_url

    origin = al.strict_origin(url)
    assert origin is not None
    host_port = origin.split("://", 1)[1]
    u3 = parse_url(url)
    yu = yarl.URL(url)
    hx = httpx.URL(url)
    default = {"http": 80, "https": 443}[origin.split(":", 1)[0]]
    expected = {(h.strip("[]"), p) for h, p in [_split(host_port)]}
    for host, port in ((u3.host, u3.port), (yu.host, yu.explicit_port or yu.port), (hx.host, hx.port or default)):
        assert (host.strip("[]").lower(), port or default) in expected, (url, host, port)


def _split(host_port: str):
    host, _, port = host_port.rpartition(":")
    return host, int(port)


def test_ttl_constant_is_env_backed_and_registered():
    from autobot_shared.env_registry import REGISTRY

    spec = REGISTRY["AUTOBOT_EGRESS_INTERNAL_ORIGINS_TTL_S"]
    assert spec.default == 60 and spec.type is int
    assert REGISTRY["AUTOBOT_EGRESS_PROVIDER_TIMEOUT_S"].default == 5


# --- never-internal hosts (#17576 review) ------------------------------------


def _patched_ssot(monkeypatch, hosts):
    urls = {
        n: f"http://{h}:8001" for n, h in zip(("backend_url", "ollama_url", "aistack_url", "npu_worker_url"), hosts)
    }
    fake = SimpleNamespace(
        tts_worker_url="http://127.0.0.1:1",
        browser_service_url="http://127.0.0.1:2",
        slm_url="http://127.0.0.1:3",
        frontend_url="http://127.0.0.1:5",
        vm=SimpleNamespace(chromadb="127.0.0.1", main="127.0.0.1", browser="127.0.0.1"),
        port=SimpleNamespace(chromadb=4, vnc=6),
        llm=SimpleNamespace(lmstudio_host="http://10.0.0.9:1234"),
        vllm_host="http://10.0.0.9:8000",
        **urls,
    )
    import autobot_shared.ssot_config as ssot

    monkeypatch.setattr(ssot, "config", fake)
    monkeypatch.setattr(
        _nc, "ServiceURLs", SimpleNamespace(PROMETHEUS_API="http://127.0.0.1:7", ALERTMANAGER_API="http://127.0.0.1:8")
    )


@pytest.mark.parametrize(
    "host",
    [
        "169.254.169.254",
        "169.254.7.7",
        "[fe80::1]",
        "[fd00:ec2::254]",
        "0.0.0.0",
        "[::]",
        "[::ffff:169.254.169.254]",
        "[::ffff:0.0.0.0]",
    ],
)
def test_link_local_metadata_and_unspecified_config_hosts_are_dropped(monkeypatch, host):
    log = MagicMock()
    monkeypatch.setattr(al, "logger", log)
    _patched_ssot(monkeypatch, [host, "127.0.0.1", "127.0.0.1", "127.0.0.1"])
    origins = al.static_internal_origins()
    assert not any(host.strip("[]") in o for o in origins)
    assert "http://127.0.0.1:8001" in origins, "loopback must stay internal (single-host default)"
    log.warning.assert_called()


@pytest.mark.asyncio
async def test_provider_cannot_smuggle_a_metadata_origin(monkeypatch, pinned_internal):
    provider = AsyncMock(return_value=["http://169.254.169.254:80", "http://[fe80::1]:8000", "http://10.9.9.9:8095"])
    al.register_internal_origin_provider(provider)
    origins = await al.internal_origins()
    assert "http://10.9.9.9:8095" in origins
    assert not [o for o in origins if "169.254" in o or "fe80" in o]
    with pytest.raises(EgressBlockedError):
        await assert_egress_policy("http://169.254.169.254/latest/meta-data/")


# --- apply_egress_guard accepts only None / bool / EGRESS_POLICY (L1) ----------


@pytest.mark.asyncio
async def test_apply_egress_guard_none_is_no_guard_and_junk_is_a_type_error():
    from autobot_shared.http_egress_guard import apply_egress_guard

    await apply_egress_guard("http://10.1.2.3/x", None)  # no guard: nothing raised
    for junk in ("yes", 1, object(), []):
        with pytest.raises(TypeError):
            await apply_egress_guard("http://10.1.2.3/x", junk)
    with pytest.raises(EgressBlockedError):
        await apply_egress_guard("http://10.1.2.3/x", False)


@pytest.mark.asyncio
async def test_prometheus_is_not_allowlisted_pending_18326(server_called):
    assert not await al.is_internal_origin("http://10.0.0.3:9090/api/v1/query")


# --- the refusal message names a setting only where the setting applies -------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("guard", [EGRESS_POLICY, "public_only_raw"])
async def test_policy_and_public_only_refusals_do_not_advertise_the_private_network_setting(pinned_internal, guard):
    with pytest.raises(EgressBlockedError) as refused:
        if guard is EGRESS_POLICY:
            await assert_egress_policy("http://10.1.2.3:8001/x")
        else:
            await assert_public_egress("http://10.1.2.3:8001/x")
    assert "AUTOBOT_CONNECTOR_PRIVATE_NETWORK_EGRESS" not in str(refused.value)
    assert "not on the SSOT internal-origin allowlist" in str(refused.value)


@pytest.mark.asyncio
async def test_bool_guard_refusal_keeps_the_private_network_hint():
    from autobot_shared.http_egress_guard import apply_egress_guard

    with pytest.raises(EgressBlockedError) as refused:
        await apply_egress_guard("http://10.1.2.3:8001/x", False)
    assert "AUTOBOT_CONNECTOR_PRIVATE_NETWORK_EGRESS=true" in str(refused.value)
