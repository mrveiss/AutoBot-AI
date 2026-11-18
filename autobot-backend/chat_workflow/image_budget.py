# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Context-budget gate for attaching a screenshot to an LLM call (#11538)."""

from __future__ import annotations


def image_fits_budget(prompt: str, model_name: str, image_token_estimate: int) -> bool:
    """True when the prompt plus the fixed per-image token cost fits the model's history budget.

    Uses ContextWindowManager's token estimate so a screenshot never silently
    blows the model's max-history-token budget.
    """
    from context_window_manager import ContextWindowManager

    mgr = ContextWindowManager()
    prompt_tokens = mgr.estimate_tokens(prompt)
    return (prompt_tokens + image_token_estimate) <= mgr.get_max_history_tokens(model_name)
