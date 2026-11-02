# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The chat workflow's budget refusal, as a message the stream can carry (#16845)."""

from __future__ import annotations

from async_chat_workflow import WorkflowMessage
from services.chat_budget_gate import CHAT_BUDGET_ERROR_CODE, ChatBudgetExceeded, enforce_chat_budget


async def budget_refusal_message() -> WorkflowMessage | None:
    """An error message naming the exhausted budget, or None when the turn may call the LLM.

    ``metadata.i18n_key`` / ``i18n_params`` let the UI render its own translation;
    ``content`` is the English fallback for API consumers.
    """
    try:
        await enforce_chat_budget()
    except ChatBudgetExceeded as exc:
        return WorkflowMessage(
            type="error",
            content=exc.message,
            metadata={
                "error": True,
                "error_code": CHAT_BUDGET_ERROR_CODE,
                "i18n_key": exc.detail["i18n_key"],
                "i18n_params": exc.detail["i18n_params"],
            },
        )
    return None
