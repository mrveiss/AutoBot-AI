# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Raw-client outbound calls in ``services/`` assert ``EGRESS_POLICY`` and refuse redirects (#17576, AC4 slice 3).

The SLM client, NPU client, fleet registry, vision step handler and the auto-research / OSINT sweeps use
aiohttp or httpx directly, so each asserts the policy on the exact URL it then requests. Three host-shaped
properties per site (network mocked): an internal SSOT origin works on a single-host loopback install, a
public URL is allowed, and a private non-allowlisted origin sends no request. Fixed vendor hosts
(arXiv, GitHub, FRED, ...) are checked by making DNS answer private: the public check then refuses them.
"""

from __future__ import annotations

import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from autobot_shared import egress_allowlist as al
from services import fleet_registry, npu_client, slm_client
from services.autoresearch import auto_research_agent, osint_engine
from services.workflow_automation import vision_step_handler as vision

INTERNAL = "http://127.0.0.1:8001"
PUBLIC = "http://api.example.test:8001"
PRIVATE = "http://10.1.2.3:8001"
PUBLIC_IP = "93.184.216.34"
PRIVATE_IP = "10.9.9.9"


def _resolve_to(monkeypatch, ip):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda host, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]
    )


@pytest.fixture(autouse=True)
def _clean_allowlist(monkeypatch):
    al.reset_internal_origin_state()
    monkeypatch.setattr(al, "_ssot_service_urls", lambda: [INTERNAL])
    _resolve_to(monkeypatch, PUBLIC_IP)
    yield
    al.reset_internal_origin_state()


def _ctx(payload):
    resp = MagicMock(status=200, status_code=200)
    resp.json = AsyncMock(return_value=payload)
    resp.raise_for_status = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _aiohttp_session(payload=None):
    session = MagicMock()
    session.get = MagicMock(return_value=_ctx(payload if payload is not None else {}))
    session.post = MagicMock(return_value=_ctx(payload if payload is not None else {}))
    return session


def _sent(session):
    return session.get.called or session.post.called


# --- SLM client -------------------------------------------------------------------------------


def _slm(base, session):
    client = slm_client.SLMClient(slm_url=base)
    client._http_session = session
    session.closed = False
    return client


async def _slm_agents(base, session):
    await _slm(base, session)._fetch_all_agents()


async def _slm_agent_llm(base, session):
    await _slm(base, session)._fetch_agent_llm_config("agent")


async def _slm_create(base, session):
    await _slm(base, session).create_deployment({})


async def _slm_get(base, session):
    await _slm(base, session).get_deployment("dep")


async def _slm_list(base, session):
    await _slm(base, session).list_deployments("node")


async def _slm_discover(base, session):
    client = _slm(base, session)
    slm_client._slm_client = client
    try:
        await slm_client._fetch_from_slm("svc")
    finally:
        slm_client._slm_client = None


# --- NPU client -------------------------------------------------------------------------------


def _npu(base, session):
    client = npu_client.NPUClient(base_url=base)
    client._get_session = AsyncMock(return_value=session)
    return client


async def _npu_health(base, session):
    await _npu(base, session).is_available(force_check=True)


async def _npu_device(base, session):
    await _npu(base, session).get_device_info()


async def _npu_embeddings(base, session):
    await _npu(base, session).generate_embeddings(["text"])


async def _npu_whisper(base, session):
    await _npu(base, session).transcribe_audio("/tmp/a.wav")


async def _npu_stats(base, session):
    await _npu(base, session).get_stats()


# --- fleet registry ---------------------------------------------------------------------------


async def _fleet(base, session):
    client = SimpleNamespace(_get_session=AsyncMock(return_value=session), _rest_url=lambda path: f"{base}{path}")
    slm_client._slm_client = client
    try:
        await fleet_registry._fetch_registry_nodes()
    finally:
        slm_client._slm_client = None


SESSION_SITES = [
    pytest.param(_slm_agents, id="slm_client.fetch_all_agents"),
    pytest.param(_slm_agent_llm, id="slm_client.fetch_agent_llm_config"),
    pytest.param(_slm_create, id="slm_client.create_deployment"),
    pytest.param(_slm_get, id="slm_client.get_deployment"),
    pytest.param(_slm_list, id="slm_client.list_deployments"),
    pytest.param(_slm_discover, id="slm_client.fetch_from_slm"),
    pytest.param(_npu_health, id="npu_client.is_available"),
    pytest.param(_npu_device, id="npu_client.get_device_info"),
    pytest.param(_npu_embeddings, id="npu_client.generate_embeddings"),
    pytest.param(_npu_whisper, id="npu_client.transcribe_audio"),
    pytest.param(_npu_stats, id="npu_client.get_stats"),
    pytest.param(_fleet, id="fleet_registry.fetch_registry_nodes"),
]


async def _drive(site, *args):
    try:
        await site(*args)
    except Exception:  # the property under test is whether a request left, not how the site reports it
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize("site", SESSION_SITES)
@pytest.mark.parametrize("base", [INTERNAL, PUBLIC], ids=["internal_ssot_origin", "public_url"])
async def test_session_site_allowed_origin_sends_the_request(site, base):
    session = _aiohttp_session()
    await _drive(site, base, session)
    assert _sent(session)


@pytest.mark.asyncio
@pytest.mark.parametrize("site", SESSION_SITES)
async def test_session_site_private_origin_sends_no_request(site):
    session = _aiohttp_session()
    await _drive(site, PRIVATE, session)
    assert not _sent(session)


@pytest.mark.asyncio
@pytest.mark.parametrize("site", SESSION_SITES)
async def test_session_site_refuses_redirects(site):
    session = _aiohttp_session()
    await _drive(site, INTERNAL, session)
    calls = [*session.get.call_args_list, *session.post.call_args_list]
    assert calls
    assert all(c.kwargs.get("allow_redirects") is False for c in calls)


# --- vision step handler ----------------------------------------------------------------------


def _httpx_client():
    instance = MagicMock()
    resp = MagicMock(status_code=200)
    resp.json = MagicMock(return_value={"elements": [{"text": "x"}], "screenshot": ""})
    resp.raise_for_status = MagicMock()
    instance.get = AsyncMock(return_value=resp)
    instance.post = AsyncMock(return_value=resp)
    ctor = MagicMock()
    ctor.return_value.__aenter__ = AsyncMock(return_value=instance)
    ctor.return_value.__aexit__ = AsyncMock(return_value=False)
    return ctor, instance


def _httpx_urls(instance):
    return [c.args[0] for c in [*instance.get.call_args_list, *instance.post.call_args_list]]


VISION_STEPS = [
    pytest.param("vision-capture", {"target": "vnc"}, "/api/vision/analyze", id="vnc_post"),
    pytest.param("vision-click", {"target": "vnc"}, "/api/vision/automation-opportunities", id="vnc_get"),
    pytest.param(
        "vision-wait",
        {"target": "vnc", "timeout": 0.02, "poll_interval": 0.01, "search_text": "x"},
        "/api/vision/elements",
        id="vnc_poll",
    ),
    pytest.param("vision-capture", {"target": "web", "browser_session_id": "s"}, "/session/action", id="web_action"),
    pytest.param("vision-ocr", {"target": "web", "browser_session_id": "s"}, "/api/vision/ocr", id="web_ocr"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("step,cfg,suffix", VISION_STEPS)
@pytest.mark.parametrize("base", [INTERNAL, PUBLIC], ids=["internal_ssot_origin", "public_url"])
async def test_vision_step_allowed_origin_sends_the_request(step, cfg, suffix, base, monkeypatch):
    ctor, instance = _httpx_client()
    monkeypatch.setattr(vision.httpx, "AsyncClient", ctor)
    await vision.execute_vision_step(step, cfg, backend_url=base)
    assert any(u.endswith(suffix) for u in _httpx_urls(instance))


@pytest.mark.asyncio
@pytest.mark.parametrize("step,cfg,suffix", VISION_STEPS)
async def test_vision_step_private_origin_sends_no_request(step, cfg, suffix, monkeypatch):
    ctor, instance = _httpx_client()
    monkeypatch.setattr(vision.httpx, "AsyncClient", ctor)
    result = await vision.execute_vision_step(step, cfg, backend_url=PRIVATE)
    assert not _httpx_urls(instance)
    assert result["success"] is False


# --- auto-research and OSINT sweeps (fixed public vendor hosts) -------------------------------


def _vendor_client():
    resp = MagicMock(status_code=200, text="")
    resp.json = MagicMock(return_value={})
    resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    return client


async def _arxiv(client):
    await auto_research_agent._search_arxiv(client, "q", 1)


async def _github(client):
    await auto_research_agent._search_github(client, "q", 1)


def _osint(source):
    async def sweep(client):
        await source().sweep(client)

    return sweep


VENDOR_SITES = [
    pytest.param(_arxiv, id="auto_research_agent.arxiv"),
    pytest.param(_github, id="auto_research_agent.github"),
    pytest.param(_osint(osint_engine.FREDSource), id="osint_engine.fred"),
    pytest.param(_osint(osint_engine.GDELTSource), id="osint_engine.gdelt"),
    pytest.param(_osint(osint_engine.NASAFIRMSSource), id="osint_engine.nasa_firms"),
    pytest.param(_osint(osint_engine.NOAASource), id="osint_engine.noaa"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("site", VENDOR_SITES)
async def test_public_vendor_host_is_allowed_and_redirects_are_refused(site):
    client = _vendor_client()
    await _drive(site, client)
    client.get.assert_awaited_once()
    assert client.get.await_args.kwargs["follow_redirects"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("site", VENDOR_SITES)
async def test_vendor_host_resolving_to_a_private_address_sends_no_request(site, monkeypatch):
    _resolve_to(monkeypatch, PRIVATE_IP)
    client = _vendor_client()
    await _drive(site, client)
    client.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_arxiv_search_reports_a_refusal_as_no_results_not_an_exception(monkeypatch):
    _resolve_to(monkeypatch, PRIVATE_IP)
    assert await auto_research_agent._search_arxiv(_vendor_client(), "q", 1) == []


# --- SLM event websocket ------------------------------------------------------------------------


async def _slm_ws(base):
    client = slm_client.SLMClient(slm_url=base, auth_token="token")
    client._shutdown = True
    await client._ws_connect_and_listen()


@pytest.mark.asyncio
@pytest.mark.parametrize("base,reached", [(INTERNAL, True), (PRIVATE, False)])
async def test_slm_websocket_handshake_is_guarded(base, reached, monkeypatch):
    if base == INTERNAL:
        al.reset_internal_origin_state()
        monkeypatch.setattr(al, "_ssot_service_urls", lambda: ["ws://127.0.0.1:8001"])
    connect = MagicMock(side_effect=RuntimeError("stop"))
    monkeypatch.setattr(slm_client, "connect_no_redirect", connect)
    await _slm_ws(base)
    assert connect.called is reached
