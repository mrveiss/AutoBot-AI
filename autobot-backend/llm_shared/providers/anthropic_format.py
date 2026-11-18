# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one Anthropic-family message split (#16815).

The Anthropic Messages API takes the system prompt as a top-level field, not as a message. The
Anthropic API (`anthropic.py`), Claude-on-Vertex (`vertexai.py`) and Claude-on-Bedrock (`bedrock.py`)
all lift it out the same way, so the split lives here and nowhere else.

Behaviour, preserved exactly from the three copies it replaced:

* the LAST `system` message wins; earlier ones are discarded;
* every other message becomes `{"role": msg.get("role", "user"), "content": msg.get("content", "")}`,
  in order (a missing key gets the default; an explicit None is kept as None);
* `content` is passed through untouched, so a content-block list (text, image, tool_use,
  tool_result) reaches the API as given and the formatter never alternates, merges or validates roles;
* a missing `system` yields `""`; the caller decides whether and how to send it (the Anthropic API
  wraps it in a cache-control block, Vertex and Bedrock send the plain string).
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from autobot_shared.ssot_constants import CategoryDefaults


def split_system_and_chat(messages: List[Dict[str, Any]]) -> Tuple[Any, List[Dict[str, Any]]]:
    """Return ``(system_content, chat_messages)`` for an Anthropic-family request."""
    system_content: Any = ""
    chat_messages: List[Dict[str, Any]] = []
    for msg in messages:
        if msg.get("role") == CategoryDefaults.ROLE_SYSTEM:
            system_content = msg.get("content", "")
        else:
            chat_messages.append(
                {"role": msg.get("role", CategoryDefaults.ROLE_USER), "content": msg.get("content", "")}
            )
    return system_content, chat_messages
