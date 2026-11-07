# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Server-chosen outbound calls in ``services/`` run under ``EGRESS_POLICY`` (#17576, AC4 slice 3).

Each converted call site is driven through its real function with a real ``HTTPClientManager``
(session mocked, no network). Three host-shaped properties per site: an internal SSOT origin works on a
single-host loopback install, a public URL (an external vendor API, or any public host) is allowed, and a
private non-allowlisted origin is refused before any request is sent.

The raw-client sites (SLM, NPU, fleet registry, vision, auto-research) are in
``egress_policy_raw_clients_17576_test.py``; the user-/DB-supplied WhatsApp URLs in
``egress_policy_user_url_services_17576_test.py``.
"""

from __future__ import annotations

import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from autobot_shared import egress_allowlist as al
from autobot_shared.http_client_manager import HTTPClientManager
from services import (
    ai_stack_client,
    command_extraction_service,
    mcp_dispatch,
    playwright_service,
    redis_service_manager,
    tts_client,
)
from services.provider_health import providers
from services.skill_management import skill_proposer, skill_ranker

INTERNAL = "http://127.0.0.1:8001"
PUBLIC = "http://api.example.test:8001"
PRIVATE = "http://10.1.2.3:8001"
PUBLIC_IP = "93.184.216.34"
HEALTHY = {"status": "healthy", "models": [], "tools": [], "data": [], "skills": []}


@pytest.fixture(autouse=True)
def _clean_allowlist():
    al.reset_internal_origin_state()
    yield
    al.reset_internal_origin_state()


@pytest.fixture
def net(monkeypatch):
    """Real manager, mocked session, a single-host loopback allowlist and mocked DNS."""
    resp = MagicMock(status=200)
    resp.json = AsyncMock(return_value=HEALTHY)
    resp.read = AsyncMock(return_value=b"")
    resp.text = AsyncMock(return_value="")
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
    monkeypatch.setattr("autobot_shared.http_client.get_http_client", lambda: mgr)
    for module in (ai_stack_client, mcp_dispatch, playwright_service, providers, skill_proposer, skill_ranker):
        monkeypatch.setattr(module, "get_http_client", lambda: mgr)
    monkeypatch.setattr(tts_client, "get_http_client", lambda: mgr)
    monkeypatch.setattr(redis_service_manager, "get_http_client", lambda: mgr)
    return SimpleNamespace(session=session, monkeypatch=monkeypatch)


def _reached(n, suffix):
    return any(suffix in str(c.args[1]) for c in n.session.request.await_args_list)


async def _ai_stack_request(n, base):
    await ai_stack_client.AIStackClient(base_url=base, enabled=True)._make_request("GET", "/x")


async def _ai_stack_health(n, base):
    client = ai_stack_client.AIStackClient(base_url=PRIVATE, enabled=True)
    client._ollama_url = base
    await client.health_check()


async def _ai_stack_agents(n, base):
    client = ai_stack_client.AIStackClient(base_url=PRIVATE, enabled=True)
    client._ollama_url = base
    await client.list_available_agents()


async def _command_extraction(n, base):
    await command_extraction_service._slm_exec("node", "ls", slm_url=base)


async def _mcp_refresh(n, base):
    n.monkeypatch.setattr(mcp_dispatch, "config", SimpleNamespace(backend_url=base))
    await mcp_dispatch.MCPDispatcher().refresh_tool_cache()


async def _mcp_bridge(n, base):
    isolated = MagicMock(get_or_create=AsyncMock(return_value=None))
    n.monkeypatch.setattr("services.mcp_isolated_runtime.get_isolated_registry", lambda: isolated)
    await mcp_dispatch.MCPDispatcher()._call_bridge("tool", "bridge", f"{base}/api/x/mcp/tool", {})


def _playwright(base):
    svc = playwright_service.PlaywrightService("127.0.0.1", 8001)
    svc.base_url = base
    return svc


async def _playwright_health(n, base):
    await _playwright(base)._health_check()


async def _playwright_post(n, base):
    await _playwright(base)._post_and_parse("search", {})


async def _playwright_screenshot(n, base):
    await _playwright(base).capture_screenshot("https://page.example.test/")


async def _playwright_status(n, base):
    await _playwright(base).get_service_status()


async def _ollama_health(n, base):
    checker = providers.OllamaHealth()
    checker.ollama_host = base
    await checker.check_health()


async def _vendor_health(cls, n, base):
    checker = cls()
    checker.api_key, checker.base_url = "key", base
    await checker.check_health()


async def _openai_health(n, base):
    await _vendor_health(providers.OpenAIHealth, n, base)


async def _anthropic_health(n, base):
    await _vendor_health(providers.AnthropicHealth, n, base)


async def _lmstudio_health(n, base):
    checker = providers.LMStudioHealth()
    checker.lmstudio_host = base
    await checker.check_health()


async def _vllm_health(n, base):
    checker = providers.VLLMHealth()
    checker.vllm_host = base
    await checker.check_health()


async def _google_health(n, base):
    await _vendor_health(providers.GoogleHealth, n, base)


def _redis_manager(base):
    return redis_service_manager.RedisServiceManager(slm_url=base, slm_node_id="node")


async def _redis_action(n, base):
    await _redis_manager(base)._slm_service_action("restart")


async def _redis_status(n, base):
    await _redis_manager(base)._slm_get_service_status()


def _policy(monkeypatch, value):
    monkeypatch.setattr(skill_proposer, "fetch_slm_policy_json", AsyncMock(return_value=value))
    monkeypatch.setattr(skill_proposer, "_disabled_logged", False)


async def _proposer(n, base):
    _policy(n.monkeypatch, {"enabled": True})
    cfg = SimpleNamespace(slm_url=base, timeout=SimpleNamespace(llm_call=5))
    n.monkeypatch.setattr(skill_proposer, "config", cfg)
    await skill_proposer.SkillProposer(slm_client=None)._send_proposal_to_slm({})


async def _ranker_skills(n, base):
    ranker = skill_ranker.SkillRanker()
    ranker.slm_host = base
    await ranker._fetch_active_skills()


async def _ranker_embedding(n, base):
    ranker = skill_ranker.SkillRanker()
    ranker.slm_host = base
    await ranker._get_embedding("text")


def _tts(base):
    return tts_client.TTSClient(base_url=base)


async def _tts_available(n, base):
    await _tts(base).is_available()


async def _tts_synthesize(n, base):
    await _tts(base).synthesize("hi")


async def _tts_stream(n, base):
    async for _ in _tts(base).synthesize_stream("hi"):
        break


async def _tts_clone(n, base):
    await _tts(base).clone_voice("hi", b"wav")


async def _tts_list(n, base):
    await _tts(base).list_voices()


async def _tts_create(n, base):
    await _tts(base).create_voice("name", b"wav")


async def _tts_delete(n, base):
    await _tts(base).delete_voice("voice")


SITES = [
    pytest.param(_ai_stack_request, "/x", id="ai_stack_client.make_request"),
    pytest.param(_ai_stack_health, "/api/tags", id="ai_stack_client.health_check_ollama"),
    pytest.param(_ai_stack_agents, "/api/tags", id="ai_stack_client.list_agents_ollama"),
    pytest.param(_command_extraction, "/exec", id="command_extraction_service.slm_exec"),
    pytest.param(_mcp_refresh, "/api/mcp/tools", id="mcp_dispatch.refresh_tool_cache"),
    pytest.param(_mcp_bridge, "/api/x/mcp/tool", id="mcp_dispatch.call_bridge"),
    pytest.param(_playwright_health, "/health", id="playwright_service.health"),
    pytest.param(_playwright_post, "/search", id="playwright_service.post_and_parse"),
    pytest.param(_playwright_screenshot, "/test-frontend", id="playwright_service.capture_screenshot"),
    pytest.param(_playwright_status, "/health", id="playwright_service.service_status"),
    pytest.param(_ollama_health, "/api/tags", id="provider_health.ollama"),
    pytest.param(_openai_health, "/models", id="provider_health.openai"),
    pytest.param(_anthropic_health, "/messages/count_tokens", id="provider_health.anthropic"),
    pytest.param(_google_health, "/models", id="provider_health.google"),
    pytest.param(_lmstudio_health, "/v1/models", id="provider_health.lmstudio"),
    pytest.param(_vllm_health, "/v1/models", id="provider_health.vllm"),
    pytest.param(_redis_action, "/restart", id="redis_service_manager.service_action"),
    pytest.param(_redis_status, "/services", id="redis_service_manager.service_status"),
    pytest.param(_proposer, "/api/skills/propose", id="skill_proposer.send"),
    pytest.param(_ranker_skills, "/api/skills/active", id="skill_ranker.active_skills"),
    pytest.param(_ranker_embedding, "/api/embeddings", id="skill_ranker.embedding"),
    pytest.param(_tts_available, "/health", id="tts_client.is_available"),
    pytest.param(_tts_synthesize, "/tts/synthesize", id="tts_client.synthesize"),
    pytest.param(_tts_stream, "/tts/synthesize/stream", id="tts_client.synthesize_stream"),
    pytest.param(_tts_clone, "/tts/clone-voice", id="tts_client.clone_voice"),
    pytest.param(_tts_list, "/voices", id="tts_client.list_voices"),
    pytest.param(_tts_create, "/voices/create", id="tts_client.create_voice"),
    pytest.param(_tts_delete, "/voices/voice", id="tts_client.delete_voice"),
]


async def _drive(site, n, base):
    """Run *site*; sites that swallow or surface a refusal are both fine, only the request matters."""
    try:
        await site(n, base)
    except Exception:  # the property under test is whether a request left, not how the site reports it
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize("site,suffix", SITES)
@pytest.mark.parametrize("base", [INTERNAL, PUBLIC], ids=["internal_ssot_origin", "public_url"])
async def test_allowed_origin_reaches_the_network(site, suffix, base, net):
    await _drive(site, net, base)
    assert _reached(net, suffix), net.session.request.await_args_list


@pytest.mark.asyncio
@pytest.mark.parametrize("site,suffix", SITES)
async def test_private_non_allowlisted_origin_is_refused_before_any_request(site, suffix, net):
    await _drive(site, net, PRIVATE)
    net.session.request.assert_not_awaited()


@pytest.mark.asyncio
async def test_vendor_api_with_a_fixed_public_base_url_is_allowed(net):
    """The Gemini base URL is a constant public host: ``EGRESS_POLICY`` passes it through the public check."""
    checker = providers.GoogleHealth()
    checker.api_key = "key"  # pragma: allowlist secret
    await checker.check_health()
    assert _reached(net, "generativelanguage.googleapis.com/v1/models")


@pytest.mark.asyncio
async def test_a_refused_target_is_reported_by_the_site_not_raised_past_it(net):
    ok, _, err = await command_extraction_service._slm_exec("node", "ls", slm_url=PRIVATE)
    assert ok is False
    assert "disallowed address" in err


@pytest.mark.asyncio
async def test_a_proposal_is_actually_sent_when_the_policy_is_on(net):
    """The manager's post is awaited and the request leaves once, with the expected URL and body."""
    _policy(net.monkeypatch, {"enabled": True})
    cfg = SimpleNamespace(slm_url=INTERNAL, timeout=SimpleNamespace(llm_call=5))
    net.monkeypatch.setattr(skill_proposer, "config", cfg)
    payload = {"name": "skill"}
    await skill_proposer.SkillProposer(slm_client=None)._send_proposal_to_slm(payload)
    net.session.request.assert_awaited_once()
    assert net.session.request.await_args.args[:2] == ("POST", f"{INTERNAL}/api/skills/propose")
    assert net.session.request.await_args.kwargs["json"] == payload


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, {}, {"enabled": False}, {"enabled": "true"}, ["enabled"]])
async def test_nothing_is_sent_unless_the_policy_explicitly_enables_it(value, net):
    _policy(net.monkeypatch, value)
    net.monkeypatch.setattr(skill_proposer, "config", SimpleNamespace(slm_url=INTERNAL))
    result = await skill_proposer.SkillProposer(slm_client=None)._send_proposal_to_slm({"name": "skill"})
    assert result == {"status": "disabled"}
    net.session.request.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_off_state_is_logged_once(net, caplog):
    _policy(net.monkeypatch, None)
    proposer = skill_proposer.SkillProposer(slm_client=None)
    with caplog.at_level("INFO"):
        await proposer._send_proposal_to_slm({})
        await proposer._send_proposal_to_slm({})
    assert sum("Skill proposals are off" in r.getMessage() for r in caplog.records) == 1


@pytest.mark.asyncio
async def test_the_old_unawaited_form_cannot_be_entered(net):
    """Contrast: ``async with manager.post(...)`` without ``await`` raises TypeError and sends nothing."""
    mgr = skill_proposer.get_http_client()
    with pytest.raises(TypeError):
        async with mgr.post(f"{INTERNAL}/api/skills/propose", json={}):
            pass
    net.session.request.assert_not_awaited()


@pytest.mark.asyncio
async def test_ai_stack_refusal_makes_exactly_one_attempt(net, monkeypatch):
    calls = []
    real = ai_stack_client.AIStackClient.__init__

    def counting(self, *a, **k):
        real(self, *a, **k)
        original = type(self.http_client).request

        async def request(manager, *args, **kwargs):
            calls.append(args)
            return await original(manager, *args, **kwargs)

        # The class, for the singleton reason given on the `net` fixture (#19527).
        monkeypatch.setattr(type(self.http_client), "request", request)

    monkeypatch.setattr(ai_stack_client.AIStackClient, "__init__", counting)
    client = ai_stack_client.AIStackClient(base_url=PRIVATE, enabled=True)
    with pytest.raises(ai_stack_client.AIStackError):
        await client._make_request("GET", "/x")
    assert len(calls) == 1
