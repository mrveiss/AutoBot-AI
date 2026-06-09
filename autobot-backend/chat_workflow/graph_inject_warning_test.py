# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for _inject_mid_conversation_warning helper (Issue #3260).

Verifies that:
1. The helper appends the hint to the prompt string with the expected format.
2. An empty prompt is handled correctly.
3. The helper returns a plain string, NOT a SystemMessage object, so it is
   safe for all LLM providers including Anthropic (which rejects SystemMessage
   after the first human turn).
4. A mock Anthropic _format_messages validator shows that a HumanMessage is
   accepted while a mid-conversation SystemMessage raises ValueError —
   confirming why the helper's prompt-string approach is correct.

This file is self-contained: all runtime dependencies that are absent from the
dev Python environment (langchain_core, langgraph, xxhash, redis) are stubbed
at module level before graph.py is loaded.  The test therefore runs with only
Python stdlib and pytest installed.
"""

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Minimal message stubs — replicate only what the tests rely on.
# langchain_core may not be installed in the dev environment.
# ---------------------------------------------------------------------------


class _BaseMessage:
    """Minimal LangChain BaseMessage stub."""

    def __init__(self, content: str) -> None:
        self.content = content


class _HumanMessage(_BaseMessage):
    """Stub for langchain_core.messages.HumanMessage."""


class _SystemMessage(_BaseMessage):
    """Stub for langchain_core.messages.SystemMessage."""


# ---------------------------------------------------------------------------
# Stub all missing runtime packages so graph.py can be loaded in isolation.
# ---------------------------------------------------------------------------

_LANGCHAIN_CORE_MESSAGES = types.ModuleType("langchain_core.messages")
_LANGCHAIN_CORE_MESSAGES.HumanMessage = _HumanMessage  # type: ignore[attr-defined]
_LANGCHAIN_CORE_MESSAGES.SystemMessage = _SystemMessage  # type: ignore[attr-defined]
_LANGCHAIN_CORE_MESSAGES.AIMessage = MagicMock  # type: ignore[attr-defined]
_LANGCHAIN_CORE_MESSAGES.BaseMessage = _BaseMessage  # type: ignore[attr-defined]

_LANGCHAIN_CORE = types.ModuleType("langchain_core")
_LANGCHAIN_CORE.messages = _LANGCHAIN_CORE_MESSAGES  # type: ignore[attr-defined]

_LANGCHAIN_CORE_RUNNABLES = types.ModuleType("langchain_core.runnables")
_LANGCHAIN_CORE_RUNNABLES.RunnableConfig = MagicMock  # type: ignore[attr-defined]

_STUBS: dict = {
    "langchain_core": _LANGCHAIN_CORE,
    "langchain_core.messages": _LANGCHAIN_CORE_MESSAGES,
    "langchain_core.runnables": _LANGCHAIN_CORE_RUNNABLES,
    "xxhash": types.ModuleType("xxhash"),
    "redis": types.ModuleType("redis"),
    "redis.asyncio": types.ModuleType("redis.asyncio"),
    "langgraph": types.ModuleType("langgraph"),
    "langgraph.checkpoint": types.ModuleType("langgraph.checkpoint"),
    "langgraph.checkpoint.redis": types.ModuleType("langgraph.checkpoint.redis"),
    "langgraph.checkpoint.redis.aio": types.ModuleType("langgraph.checkpoint.redis.aio"),
    "langgraph.graph": types.ModuleType("langgraph.graph"),
    "langgraph.types": types.ModuleType("langgraph.types"),
    "typing_extensions": types.ModuleType("typing_extensions"),
}

for _mod_name, _stub in _STUBS.items():
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = _stub

# Provide symbols that graph.py imports at module level.
for _attr in ("END", "START", "StateGraph"):
    if not hasattr(sys.modules["langgraph.graph"], _attr):
        setattr(sys.modules["langgraph.graph"], _attr, MagicMock())
if not hasattr(sys.modules["langgraph.types"], "interrupt"):
    sys.modules["langgraph.types"].interrupt = MagicMock()  # type: ignore[attr-defined]
if not hasattr(sys.modules["langgraph.checkpoint.redis.aio"], "AsyncRedisSaver"):
    sys.modules["langgraph.checkpoint.redis.aio"].AsyncRedisSaver = MagicMock()  # type: ignore[attr-defined]

# typing_extensions.TypedDict — graph.py uses it for ChatState.
import typing

if not hasattr(sys.modules["typing_extensions"], "TypedDict"):
    sys.modules["typing_extensions"].TypedDict = typing.TypedDict  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# Load graph.py as an isolated module (bypassing chat_workflow/__init__.py).
# This avoids the full manager/dependency_container/llm_shared chain.
# ---------------------------------------------------------------------------

_GRAPH_PATH = Path(__file__).parent / "graph.py"
_spec = importlib.util.spec_from_file_location("_graph_isolated", _GRAPH_PATH)
assert _spec is not None and _spec.loader is not None
_graph_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_graph_module)  # type: ignore[union-attr]

_inject_mid_conversation_warning = _graph_module._inject_mid_conversation_warning

# Use our stub message classes for the Anthropic constraint tests.
HumanMessage = _HumanMessage
SystemMessage = _SystemMessage


class TestInjectMidConversationWarning:
    """Tests for _inject_mid_conversation_warning."""

    def test_appends_hint_to_prompt(self):
        """Helper appends the hint in a [Guidance: ...] block."""
        result = _inject_mid_conversation_warning("Avoid repeating tool calls.", "Answer the question.")
        assert result == "Answer the question.\n\n[Guidance: Avoid repeating tool calls.]"

    def test_empty_prompt(self):
        """Helper works when initial_prompt is empty."""
        result = _inject_mid_conversation_warning("Warning text.", "")
        assert result == "\n\n[Guidance: Warning text.]"

    def test_returns_string_not_message_object(self):
        """Result must be a plain string, not a LangChain message object.

        The Anthropic API rejects SystemMessage objects that appear after the
        first human turn.  Returning a plain string ensures the content is
        folded into the prompt and forwarded as part of the HumanMessage on
        the next iteration — never as a standalone SystemMessage.
        """
        hint = "Loop detected: change your approach."
        prompt = "Tell me about Python."
        result = _inject_mid_conversation_warning(hint, prompt)
        assert isinstance(result, str), (
            "_inject_mid_conversation_warning must return a str, not a " "LangChain message object (see Issue #3260)"
        )
        assert "[Guidance:" in result

    def test_multi_line_prompt_preserved(self):
        """Multi-line prompts are not truncated."""
        prompt = "Line one.\nLine two.\nLine three."
        result = _inject_mid_conversation_warning("Be concise.", prompt)
        assert result.startswith(prompt)
        assert result.endswith("[Guidance: Be concise.]")

    def test_hint_label_is_guidance(self):
        """The injected label is exactly '[Guidance: ...]' for consistency."""
        result = _inject_mid_conversation_warning("some hint", "base")
        assert "[Guidance: some hint]" in result


class TestAnthropicSystemMessageConstraint:
    """Demonstrate the Anthropic mid-conversation SystemMessage restriction.

    These tests use a mock that simulates langchain_anthropic's validation
    behaviour: a SystemMessage after the first human turn is rejected, while a
    HumanMessage (or prompt-string injection) is accepted.  This documents
    *why* _inject_mid_conversation_warning exists and what it prevents.
    """

    def _mock_format_messages(self, messages):
        """Simulate the Anthropic _format_messages validation rule.

        Anthropic only allows a SystemMessage as the *first* message.  Any
        SystemMessage appearing after a HumanMessage raises ValueError, mirroring
        ``langchain_anthropic.chat_models.ChatAnthropic._format_messages()``.
        """
        seen_human = False
        for msg in messages:
            if isinstance(msg, HumanMessage):
                seen_human = True
            if isinstance(msg, SystemMessage) and seen_human:
                raise ValueError(
                    "Anthropic does not support system messages after the first "
                    "human turn. Use a HumanMessage or append to the prompt string."
                )
        return messages

    def test_mid_conversation_system_message_rejected(self):
        """A SystemMessage after a HumanMessage raises ValueError (Anthropic rule)."""
        messages = [
            SystemMessage(content="You are a helpful assistant."),
            HumanMessage(content="Hello"),
            SystemMessage(content="[Warning: loop detected]"),  # mid-conversation — WRONG
        ]
        with pytest.raises(ValueError, match="Anthropic does not support system messages"):
            self._mock_format_messages(messages)

    def test_human_message_injection_accepted(self):
        """A HumanMessage injected mid-conversation is accepted."""
        messages = [
            SystemMessage(content="You are a helpful assistant."),
            HumanMessage(content="Hello"),
            HumanMessage(content="[System Notice]: Loop detected — change approach."),
        ]
        # Must not raise
        result = self._mock_format_messages(messages)
        assert len(result) == 3

    def test_prompt_string_injection_accepted(self):
        """Prompt-string injection (_inject_mid_conversation_warning approach) is accepted.

        The helper merges the warning into the prompt text, so the next LLM
        call carries the guidance inside a HumanMessage rather than adding a
        separate SystemMessage.
        """
        base_prompt = "Tell me about Python."
        warning = "Loop detected: change your approach."
        enriched_prompt = _inject_mid_conversation_warning(warning, base_prompt)

        messages = [
            SystemMessage(content="You are a helpful assistant."),
            HumanMessage(content=enriched_prompt),  # guidance is part of the human turn
        ]
        # Must not raise
        result = self._mock_format_messages(messages)
        assert len(result) == 2
        assert "[Guidance:" in result[1].content
