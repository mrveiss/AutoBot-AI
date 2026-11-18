# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A current model gets adaptive thinking with no ``budget_tokens``; an older one keeps the budget (#20884)."""

from autobot_shared.ssot_claude_models import CLAUDE_FABLE, CLAUDE_HAIKU, CLAUDE_OPUS, CLAUDE_SONNET
from llm_shared.providers.anthropic_request import thinking_request_kwargs


def test_a_5x_id_yields_the_adaptive_form_and_no_budget_tokens():
    for model in (CLAUDE_SONNET, CLAUDE_OPUS, CLAUDE_FABLE, CLAUDE_HAIKU):
        kwargs = thinking_request_kwargs(model, 8000)
        assert kwargs["thinking"] == {"type": "adaptive"}
        assert "budget_tokens" not in str(kwargs)
        assert kwargs["output_config"] == {"effort": "high"}
        assert "betas" not in kwargs


def test_a_pre_4_6_id_keeps_budget_tokens():
    kwargs = thinking_request_kwargs("claude-sonnet-4-20250514", 8000)
    assert kwargs["thinking"] == {"type": "enabled", "budget_tokens": 8000}
    assert kwargs["betas"] == ["interleaved-thinking-2025-05-14"]


def test_the_chat_workflow_sender_uses_the_same_predicate():
    from chat_workflow.reasoning_kwargs import _thinking_kwargs

    adaptive = _thinking_kwargs(CLAUDE_SONNET, 10000)
    assert adaptive["thinking"] == {"type": "adaptive"} and "budget_tokens" not in str(adaptive)
    assert _thinking_kwargs("claude-sonnet-4-20250514", 10000)["thinking"]["budget_tokens"] == 10000
