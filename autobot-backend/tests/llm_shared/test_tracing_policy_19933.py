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


class TestDestination:
    def test_external_refused_by_default(self, monkeypatch):
        from llm_shared.observability.tracing_policy import destination_allowed

        monkeypatch.delenv("AUTOBOT_LLM_TRACING_ALLOW_EXTERNAL", raising=False)
        assert destination_allowed("langsmith", "https://api.smith.langchain.com") is False

    def test_public_allowed_with_opt_in(self, monkeypatch):
        from llm_shared.observability import tracing_policy

        monkeypatch.setenv("AUTOBOT_LLM_TRACING_ALLOW_EXTERNAL", "true")
        with patch.object(tracing_policy, "is_public_url", return_value=True):
            assert tracing_policy.destination_allowed("langsmith", "https://t.example.com") is True

    def test_non_public_refused_even_with_opt_in(self, monkeypatch):
        from llm_shared.observability import tracing_policy

        monkeypatch.setenv("AUTOBOT_LLM_TRACING_ALLOW_EXTERNAL", "true")
        with patch.object(tracing_policy, "is_public_url", return_value=False):
            assert tracing_policy.destination_allowed("langfuse", "http://169.254.169.254:80") is False

    def test_internal_origin_allowed_without_opt_in(self, monkeypatch):
        from llm_shared.observability import tracing_policy

        monkeypatch.delenv("AUTOBOT_LLM_TRACING_ALLOW_EXTERNAL", raising=False)
        with patch.object(tracing_policy, "static_internal_origins", return_value=frozenset({"http://lf:3000"})):
            assert tracing_policy.destination_allowed("langfuse", "http://lf:3000") is True

    def test_log_never_carries_a_key(self, monkeypatch, caplog):
        from llm_shared.observability.tracing_policy import destination_allowed

        monkeypatch.delenv("AUTOBOT_LLM_TRACING_ALLOW_EXTERNAL", raising=False)
        destination_allowed("langsmith", "https://user:" + "pw" + "-hidden@api.example.com/x?api_key=zzz")
        assert "pw-hidden" not in caplog.text and "zzz" not in caplog.text
