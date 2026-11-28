# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Maps between ``modern_ai_integration`` requests and ``LLMService.chat()`` (#19649).

Split out of ``modern_ai_integration`` (over its size ceiling); takes the request and
response by duck type so it needs no import back from it.
"""

from typing import Any, Dict, List

from autobot_shared.ssot_constants import CategoryDefaults


def build_chat_messages(request: Any) -> List[Dict[str, str]]:
    """OpenAI-format messages for an ``AIRequest``: optional system turn, then the prompt."""
    system = (
        [{"role": CategoryDefaults.ROLE_SYSTEM, "content": request.system_message}] if request.system_message else []
    )
    return [*system, {"role": CategoryDefaults.ROLE_USER, "content": request.prompt}]


def ai_response_fields(llm_resp: Any) -> Dict[str, Any]:
    """The ``AIResponse`` fields an ``LLMResponse`` supplies."""
    return {
        "model_name": llm_resp.model,
        "content": llm_resp.content,
        "usage": llm_resp.usage or {"prompt_tokens": 0, "completion_tokens": 0},
        "finish_reason": llm_resp.finish_reason,
        "metadata": llm_resp.metadata or {},
    }
