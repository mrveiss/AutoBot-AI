# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for RAGAgent.generate_response (MVA-40 / GitHub #6876).

The legacy `generate_response()` method on the RAG agent was missing,
causing `api/knowledge_search_scoped.py` to raise an AttributeError that
bubbled up as a 500 response. These tests pin the new contract:

- correct shape (dict with a "response" key),
- success path delegates to the underlying LLM interface,
- failure path returns a safe error payload (no exception leakage).
"""

from typing import Any
from unittest.mock import AsyncMock

import pytest

try:
    import agents.rag_agent as _rag_mod

    RAGAgent = _rag_mod.RAGAgent
    _IMPORT_OK = True
except Exception:
    _IMPORT_OK = False

pytestmark = pytest.mark.skipif(not _IMPORT_OK, reason="rag_agent dep chain unavailable in this env")


def _build_agent(llm_interface: Any, model_name: str = "test-model"):
    """Instantiate RAGAgent bypassing __init__ to avoid SSOT/config dep chain."""
    agent = object.__new__(RAGAgent)
    agent.llm_interface = llm_interface
    agent.model_name = model_name
    return agent


def _make_llm(response_content: str = "Synthesized answer."):
    llm = type("LLM", (), {})()
    llm.chat = AsyncMock(return_value={"message": {"content": response_content}})
    return llm


@pytest.mark.asyncio
async def test_generate_response_success_returns_dict_with_response_key():
    agent = _build_agent(_make_llm("Synthesized answer."))
    result = await agent.generate_response(query="What is X?", context="X is a thing.")

    assert isinstance(result, dict)
    assert result["status"] == "success"
    assert result["response"] == "Synthesized answer."
    assert result["agent_type"] == "rag"
    assert result["model_used"] == "test-model"

    llm = agent.llm_interface
    llm.chat.assert_awaited_once()
    sent_messages = llm.chat.await_args.kwargs["messages"]
    assert any("X is a thing." in m["content"] for m in sent_messages)
    assert sent_messages[-1] == {"role": "user", "content": "What is X?"}


@pytest.mark.asyncio
async def test_generate_response_swallows_llm_errors_and_returns_safe_payload():
    """Stack traces must not leak; the method returns a generic error dict."""
    llm = type("LLM", (), {})()
    llm.chat = AsyncMock(side_effect=RuntimeError("internal traceback detail"))
    agent = _build_agent(llm)

    result = await agent.generate_response(query="hi", context="ctx")

    assert result["status"] == "error"
    assert "response" in result
    assert "traceback" not in result["response"].lower()
    assert "internal traceback detail" not in result["response"]
    assert result["agent_type"] == "rag"


@pytest.mark.asyncio
async def test_generate_response_rejects_empty_query():
    llm = type("LLM", (), {})()
    llm.chat = AsyncMock()
    agent = _build_agent(llm)

    result = await agent.generate_response(query="   ", context="ctx")

    assert result["status"] == "error"
    assert "response" in result
    llm.chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_response_accepts_missing_context():
    llm = _make_llm("ok")
    agent = _build_agent(llm)

    result = await agent.generate_response(query="hi")

    assert result["status"] == "success"
    assert result["response"] == "ok"
