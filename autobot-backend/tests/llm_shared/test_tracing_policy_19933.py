# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What the LLM tracing observers actually send, and where they may send it (#19933)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pytest

KEY = "sk-" + "Zq7" * 14  # built at runtime: a literal key trips the secret scanner
PRIVATE_TEXT = "quarterly payroll for ACME"


@dataclass
class Req:
    request_id: str = "r1"
    model_name: str = "m"
    messages: list = field(default_factory=lambda: [{"role": "user", "content": f"{PRIVATE_TEXT} api_key={KEY}"}])
    metadata: dict = field(default_factory=dict)
    llm_type: str = "general"


@dataclass
class Resp:
    request_id: str = "r1"
    content: str = f"{PRIVATE_TEXT} token {KEY}"
    usage: dict = field(default_factory=dict)
    finish_reason: str = "stop"
    provider: str = "p"
    error: str | None = None
    tool_calls: list = field(default_factory=list)


def _sent(mock) -> str:
    return repr(mock.mock_calls)


def _langsmith():
    from llm_shared.observability.langsmith_observer import LangSmithObserver
    from llm_shared.observability.tracing_config import LangSmithTracingConfig

    client = MagicMock()
    with patch.dict("sys.modules", {"langsmith": MagicMock(Client=MagicMock(return_value=client))}):
        obs = LangSmithObserver(LangSmithTracingConfig(api_url="http://x", api_key="k"))
    return obs, client


def _langfuse():
    from llm_shared.observability.langfuse_observer import LangFuseObserver
    from llm_shared.observability.tracing_config import LangFuseTracingConfig

    client = MagicMock()
    with patch.dict("sys.modules", {"langfuse": MagicMock(Langfuse=MagicMock(return_value=client))}):
        obs = LangFuseObserver(LangFuseTracingConfig(host="http://x", public_key="p", secret_key="s"))
    return obs, client


def _drive(obs) -> None:
    asyncio.run(obs.on_request(Req(), {}))
    asyncio.run(obs.on_response(Resp(), 1.0, 0.0))


@pytest.mark.parametrize("factory", [_langsmith, _langfuse])
def test_default_sends_no_prompt_or_response_text(factory, monkeypatch):
    monkeypatch.delenv("AUTOBOT_LLM_TRACING_INCLUDE_CONTENT", raising=False)
    obs, client = factory()
    _drive(obs)
    sent = _sent(client) + _sent(client.generation.return_value) if factory is _langfuse else _sent(client)
    assert PRIVATE_TEXT not in sent and KEY not in sent
    assert "content omitted" in sent


@pytest.mark.parametrize("factory", [_langsmith, _langfuse])
def test_opt_in_sends_text_with_credentials_redacted(factory, monkeypatch):
    monkeypatch.setenv("AUTOBOT_LLM_TRACING_INCLUDE_CONTENT", "true")
    obs, client = factory()
    _drive(obs)
    sent = _sent(client) + _sent(client.generation.return_value) if factory is _langfuse else _sent(client)
    assert PRIVATE_TEXT in sent
    assert KEY not in sent


@pytest.mark.parametrize("factory", [_langsmith, _langfuse])
def test_error_text_is_not_sent_by_default(factory, monkeypatch):
    monkeypatch.delenv("AUTOBOT_LLM_TRACING_INCLUDE_CONTENT", raising=False)
    obs, client = factory()
    asyncio.run(obs.on_request(Req(), {}))
    asyncio.run(obs.on_error(RuntimeError(f"echoed {PRIVATE_TEXT}"), Req()))
    sent = _sent(client) + _sent(client.generation.return_value)
    assert PRIVATE_TEXT not in sent


LISTED = "http://lf.example:3000"


@pytest.fixture()
def listed(monkeypatch):
    monkeypatch.setenv("AUTOBOT_LLM_TRACING_ALLOWED_ORIGINS", LISTED + ", https://[::1]:3000, http://[fe80::1]:3000")
    monkeypatch.delenv("AUTOBOT_LLM_TRACING_ALLOW_EXTERNAL", raising=False)


def _allowed(url: str) -> bool:
    from llm_shared.observability.tracing_policy import destination_allowed

    return destination_allowed("langfuse", url)


class TestDestination:
    def test_external_refused_by_default(self, monkeypatch):
        monkeypatch.delenv("AUTOBOT_LLM_TRACING_ALLOW_EXTERNAL", raising=False)
        monkeypatch.delenv("AUTOBOT_LLM_TRACING_ALLOWED_ORIGINS", raising=False)
        assert _allowed("https://api.smith.langchain.com") is False

    def test_public_allowed_with_opt_in(self, monkeypatch):
        from llm_shared.observability import tracing_policy

        monkeypatch.setenv("AUTOBOT_LLM_TRACING_ALLOW_EXTERNAL", "true")
        with patch.object(tracing_policy, "is_public_url", return_value=True):
            assert _allowed("https://t.example.com") is True

    def test_non_public_refused_even_with_opt_in(self, monkeypatch):
        from llm_shared.observability import tracing_policy

        monkeypatch.setenv("AUTOBOT_LLM_TRACING_ALLOW_EXTERNAL", "true")
        with patch.object(tracing_policy, "is_public_url", return_value=False):
            assert _allowed("http://private.example:3000") is False

    def test_listed_private_origin_allowed_without_opt_in(self, listed):
        assert _allowed(LISTED + "/api") is True

    def test_ssot_service_origin_is_not_trusted(self, listed, monkeypatch):
        from autobot_shared import egress_allowlist

        monkeypatch.setattr(
            egress_allowlist, "static_internal_origins", lambda: frozenset({"http://llm.example:11434"})
        )
        assert _allowed("http://llm.example:11434") is False

    @pytest.mark.parametrize(
        "url",
        [
            "http://evil.example\\@lf.example:3000",  # backslash: clients send to evil.example
            "http://user:x@lf.example:3000",  # userinfo
            "http://lf.example.:3000",  # trailing dot is a different origin
            "http://lf.example:03000",  # zero-padded port
            "http://lf.example:3001",  # other port
            "https://lf.example:3000",  # other scheme
            "http://[fe80::1]:3000",  # listed but link-local: never allowed
            "http://169.254.169.254:80",  # metadata
        ],
    )
    def test_non_matching_shapes_are_refused(self, listed, url):
        assert _allowed(url) is False

    @pytest.mark.parametrize("url", ["HTTP://LF.Example:3000/x", "https://[::1]:3000/"])
    def test_case_and_ipv6_match_exactly(self, listed, url):
        assert _allowed(url) is True

    def test_log_never_carries_a_key(self, monkeypatch, caplog):
        monkeypatch.delenv("AUTOBOT_LLM_TRACING_ALLOW_EXTERNAL", raising=False)
        _allowed("https://user:" + "pw" + "-hidden@api.example.com/x?api_key=zzz")
        assert "pw-hidden" not in caplog.text and "zzz" not in caplog.text


class TestOutboundPolicy:
    def test_blocked_pii_sends_the_marker_and_does_not_raise(self, monkeypatch):
        from a2a.pii_pipeline import PIIBlocked, PIIType
        from llm_shared.observability import tracing_policy

        monkeypatch.setenv("AUTOBOT_LLM_TRACING_INCLUDE_CONTENT", "true")
        err = PIIBlocked([next(iter(PIIType))])
        with patch.object(tracing_policy, "scrub_outbound", side_effect=err):
            assert tracing_policy.trace_text("anything") == tracing_policy.CONTENT_OMITTED
            assert tracing_policy.trace_messages([{"content": "x"}]) == tracing_policy.CONTENT_OMITTED

    def test_content_goes_through_the_outbound_pipeline(self, monkeypatch):
        from llm_shared.observability import tracing_policy

        monkeypatch.setenv("AUTOBOT_LLM_TRACING_INCLUDE_CONTENT", "true")
        with patch.object(tracing_policy, "scrub_outbound") as scrub:
            scrub.return_value.text = "SCRUBBED"
            assert tracing_policy.trace_messages([{"role": "user", "content": "hi"}])[0]["content"] == "SCRUBBED"
            assert tracing_policy.trace_text("hi") == "SCRUBBED"

    @pytest.mark.parametrize("value", ["agent-7", "run_01:a.b"])
    def test_id_tokens_pass(self, value):
        from llm_shared.observability.tracing_policy import trace_ident

        assert trace_ident(value) == value

    @pytest.mark.parametrize("value", ["call me at home", "x" * 200, "a\nb", 7, None])
    def test_free_text_ids_are_dropped(self, value):
        from llm_shared.observability.tracing_policy import trace_ident

        assert trace_ident(value) is None

    @pytest.mark.parametrize("factory", [_langsmith, _langfuse])
    def test_free_text_run_id_is_not_sent(self, factory):
        obs, client = factory()
        req = Req(metadata={"agent_id": "free text pii", "run_id": "more free text"})
        asyncio.run(obs.on_request(req, {}))
        assert "free text" not in _sent(client) + _sent(client.generation.return_value)


class TestOtelErrorText:
    def test_error_text_is_withheld_from_span_status_and_event(self, monkeypatch):
        from llm_shared.observability import otel_observer

        monkeypatch.delenv("AUTOBOT_LLM_TRACING_INCLUDE_CONTENT", raising=False)
        span = MagicMock()
        tracer = MagicMock()
        tracer.start_as_current_span.return_value.__enter__.return_value = span
        with patch.object(otel_observer, "_tracer", tracer):
            asyncio.run(otel_observer.OTELObserver().on_error(RuntimeError(f"echoed {PRIVATE_TEXT}"), Req()))
        assert PRIVATE_TEXT not in repr(span.mock_calls)
        span.record_exception.assert_not_called()
