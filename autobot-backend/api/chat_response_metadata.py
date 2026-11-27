# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Response metadata derived from an LLM response (moved out of ``api/chat.py``, which may not grow)."""

from typing import Any

from api.schemas_chat import ThinkingMetadata


def thinking_metadata_of(llm_response: Any) -> ThinkingMetadata | None:
    """MVA-3090: the thinking metadata of a response (None when there is no usage to read)."""
    if not (llm_response and llm_response.usage):
        return None
    # Check for thinking_tokens in usage dict (Anthropic extended thinking)
    thinking_tokens = llm_response.usage.get("thinking_tokens") or llm_response.usage.get("cache_read_input_tokens")
    if thinking_tokens and thinking_tokens > 0:
        return ThinkingMetadata(used=True, tokens_used=thinking_tokens)
    return ThinkingMetadata(used=False, tokens_used=None)
