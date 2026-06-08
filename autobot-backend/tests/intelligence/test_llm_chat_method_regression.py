# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Regression tests for GH #6876 — generate_response() called on LLMInterface.

Linked issue: https://github.com/mrveiss/AutoBot-AI/issues/6876

IntelligentAgent._get_llm_analysis() and StreamingCommandExecutor
._provide_progress_commentary() / ._provide_completion_commentary() used to
call self.llm_interface.generate_response(), which does not exist on
LLMInterface (or its facade). This caused AttributeError in production.

Fix (Phase 2D of #3185): replaced with self.llm_interface.chat([...]).

Regression guarantee: these tests use a strict mock that ONLY exposes chat()
(no generate_response). If the code is reverted to call generate_response(),
the mock raises AttributeError and the test fails.
"""

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Backend root is three levels up from this test file:
# tests/intelligence/test_*.py → tests/intelligence/ → tests/ → autobot-backend/
_BACKEND_ROOT = Path(__file__).parent.parent.parent


# ── strict LLM mock without generate_response() ──────────────────────────────


class _ChatOnlyLLM:
    """LLM interface stub that exposes chat() but NOT generate_response().

    Accessing generate_response() on this class raises AttributeError,
    which is exactly what happened in production with the real LLMInterface.
    Any code path that still calls generate_response() will trigger that
    AttributeError and fail the test.
    """

    def __init__(self, content: str = "Test AI response"):
        self._content = content
        self.chat_calls: list = []

    async def chat(self, messages, temperature=0.5, max_tokens=100, **kwargs):
        self.chat_calls.append({"messages": messages, "temperature": temperature, "max_tokens": max_tokens})
        resp = MagicMock()
        resp.content = self._content
        return resp

    def __getattr__(self, name):
        # Everything other than chat raises AttributeError — mirrors LLMInterface.
        raise AttributeError(
            f"'_ChatOnlyLLM' object has no attribute '{name}'. "
            f"GH #6876 regression: code must call chat(), not {name}()."
        )


# ── module loader helpers ─────────────────────────────────────────────────────


def _load_module(relative_path: str, module_alias: str):
    """Load a backend module by relative path, returning (spec, module).

    Returns (None, None) if the module's dep chain is unavailable — callers
    should call pytest.skip() in that case.
    """
    spec = importlib.util.spec_from_file_location(module_alias, relative_path)
    if spec is None or spec.loader is None:
        return None, None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:
        return None, exc
    return spec, mod


def _bypass_init(cls, **attrs):
    """Instantiate cls without calling __init__, then set attrs directly."""
    obj = object.__new__(cls)
    for k, v in attrs.items():
        setattr(obj, k, v)
    return obj


# ── GH #6876 regression: IntelligentAgent._get_llm_analysis ─────────────────


class TestIntelligentAgentGetLLMAnalysis:
    """_get_llm_analysis() must use chat(), not generate_response()."""

    @pytest.mark.asyncio
    async def test_uses_chat_not_generate_response(self):
        spec, mod = _load_module(
            str(_BACKEND_ROOT / "intelligence" / "intelligent_agent.py"),
            "intelligent_agent_under_test",
        )
        if mod is None or not isinstance(mod, type(importlib.util)):
            pytest.skip(f"intelligent_agent dep chain unavailable: {mod}")

        llm = _ChatOnlyLLM(content="Analysis result from chat()")
        agent = _bypass_init(mod.IntelligentAgent, llm_interface=llm, state=MagicMock())

        result = await agent._get_llm_analysis("list running processes")

        assert llm.chat_calls, "_get_llm_analysis() must call llm_interface.chat()"
        assert result == "Analysis result from chat()", f"Expected content from chat(), got: {result!r}"

    @pytest.mark.asyncio
    async def test_chat_receives_messages_list(self):
        spec, mod = _load_module(
            str(_BACKEND_ROOT / "intelligence" / "intelligent_agent.py"),
            "intelligent_agent_under_test_2",
        )
        if mod is None or not isinstance(mod, type(importlib.util)):
            pytest.skip(f"intelligent_agent dep chain unavailable: {mod}")

        llm = _ChatOnlyLLM()
        agent = _bypass_init(mod.IntelligentAgent, llm_interface=llm, state=MagicMock())

        await agent._get_llm_analysis("test goal")

        assert len(llm.chat_calls) == 1
        call = llm.chat_calls[0]
        assert isinstance(call["messages"], list), "chat() must receive a messages list"
        assert any(m.get("role") for m in call["messages"]), "Each message in the list must have a 'role' key"


# ── GH #6876 regression: StreamingCommandExecutor commentary methods ──────────


class TestStreamingExecutorCommentaryMethods:
    """Commentary methods must use chat(), not generate_response()."""

    @pytest.fixture(autouse=True)
    def _load_executor_module(self):
        spec, mod = _load_module(
            str(_BACKEND_ROOT / "intelligence" / "streaming_executor.py"),
            "streaming_executor_under_test",
        )
        if mod is None or not isinstance(mod, type(importlib.util)):
            pytest.skip(f"streaming_executor dep chain unavailable: {mod}")
        self._mod = mod

    def _make_executor(self, content="Commentary text"):
        llm = _ChatOnlyLLM(content=content)
        validator = MagicMock()
        validator.is_command_safe.return_value = True
        executor = _bypass_init(
            self._mod.StreamingCommandExecutor,
            llm_interface=llm,
            command_validator=validator,
            active_processes={},
            _max_processes=10,
        )
        return executor, llm

    @pytest.mark.asyncio
    async def test_progress_commentary_uses_chat(self):
        """_provide_progress_commentary must call chat(), not generate_response()."""
        executor, llm = self._make_executor("Progress update via chat()")

        chunks = []
        async for chunk in executor._provide_progress_commentary(
            recent_output="Installing package...", user_goal="install numpy"
        ):
            chunks.append(chunk)

        assert llm.chat_calls, (
            "_provide_progress_commentary() must call llm_interface.chat() "
            "(GH #6876 regression: was calling nonexistent generate_response())"
        )

    @pytest.mark.asyncio
    async def test_completion_commentary_uses_chat(self):
        """_provide_completion_commentary must call chat(), not generate_response()."""
        executor, llm = self._make_executor("Completion summary via chat()")

        chunks = []
        async for chunk in executor._provide_completion_commentary(
            command="pip install numpy", user_goal="install numpy", execution_time=1.5
        ):
            chunks.append(chunk)

        assert llm.chat_calls, (
            "_provide_completion_commentary() must call llm_interface.chat() "
            "(GH #6876 regression: was calling nonexistent generate_response())"
        )

    @pytest.mark.asyncio
    async def test_progress_commentary_skips_empty_output(self):
        """Empty output must produce no chunks — guards against spurious LLM calls."""
        executor, llm = self._make_executor()

        chunks = []
        async for chunk in executor._provide_progress_commentary(recent_output="   ", user_goal="install numpy"):
            chunks.append(chunk)

        assert not chunks, "Empty output must not produce any commentary chunks."
        assert not llm.chat_calls, "Empty output must not trigger an LLM call."

    @pytest.mark.asyncio
    async def test_commentary_returns_skip_gracefully(self):
        """When LLM returns 'SKIP', no chunk should be yielded."""
        executor, llm = self._make_executor(content="SKIP")

        chunks = []
        async for chunk in executor._provide_progress_commentary(
            recent_output="boring log line", user_goal="run tests"
        ):
            chunks.append(chunk)

        assert not chunks, "LLM SKIP response must produce no commentary chunks."
