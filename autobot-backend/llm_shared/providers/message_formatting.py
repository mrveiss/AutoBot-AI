# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical-to-wire conversion for the provider request payloads (#16815).

The canonical shape is ``LLMRequest.messages`` (role/content dicts) and
``ToolDefinition``. The provider wire formats genuinely differ, so each
format has ONE converter here and every provider that speaks that format
calls it:

* Anthropic Messages format (``anthropic``, Claude-on-Vertex, Claude-on-Bedrock):
  ``split_system_messages`` + ``anthropic_tool_schemas``.
* OpenAI function-tool format (``openai_compatible`` and its subclasses,
  ``mistral``, ``ollama``): ``openai_function_tool_schemas``.

Pure functions, no SDK, no I/O: the payload each produces is byte-identical
to what the inlined copies produced (see ``message_formatting_test.py``).
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from autobot_shared.ssot_constants import CategoryDefaults


def split_system_messages(messages: Sequence[Dict[str, Any]]) -> tuple[str, List[Dict[str, Any]]]:
    """Separate the system message from conversational messages (Anthropic format).

    The LAST system message wins (earlier ones are dropped); every other
    message keeps only ``role`` (default ``"user"``) and ``content``
    (default ``""``).
    """
    system_content = ""
    chat_messages: List[Dict[str, Any]] = []
    for msg in messages:
        if msg.get("role") == CategoryDefaults.ROLE_SYSTEM:
            system_content = msg.get("content", "")
        else:
            chat_messages.append(
                {"role": msg.get("role", CategoryDefaults.ROLE_USER), "content": msg.get("content", "")}
            )
    return system_content, chat_messages


def anthropic_tool_schemas(tools: Sequence[Any]) -> List[Dict[str, Any]]:
    """Map ToolDefinition objects to Anthropic ``tools`` entries."""
    return [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools]


def openai_function_tool_schemas(tools: Sequence[Any]) -> List[Dict[str, Any]]:
    """Map ToolDefinition objects to OpenAI function-tool dicts."""
    return [
        {
            "type": "function",
            "function": {"name": t.name, "description": t.description, "parameters": t.input_schema},
        }
        for t in tools
    ]


__all__ = ["anthropic_tool_schemas", "openai_function_tool_schemas", "split_system_messages"]
