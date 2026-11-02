# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The chat workflow's budget refusal, as a message the stream can carry (#16845)."""

from __future__ import annotations

from async_chat_workflow import WorkflowMessage
from services.chat_budget_gate import (
    CHAT_BUDGET_ERROR_CODE,
    I18N_DETAIL_KEYS,
    ChatBudgetExceeded,
    enforce_chat_budget,
)


async def budget_refusal_message() -> WorkflowMessage | None:
    """An error message naming the exhausted budget, or None when the turn may call the LLM.

    ``metadata.i18n_key`` / ``i18n_params`` / ``i18n_param_keys`` let the UI render its
    own translation; ``content`` is the English fallback for API consumers.

    Why this gate records no spend of its own (#16924 exemption): the call it guards,
    ``_process_single_llm_iteration``, posts to ``backend.llm.ollama.endpoint`` (or the
    per-model ``gpu_endpoint``) with ``/api/generate`` appended, in Ollama's request
    shape, and sends no credentials. It cannot reach a metered provider API (those need
    an auth header and a different protocol), so there is no per-token bill to record;
    only an operator pointing that setting at a credential-less Ollama-compatible proxy
    would make it metered, and nothing in this code can tell. A policy therefore trips on
    the user's other spend (LLMService, compat, compare), not on this call's own.
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
                **{key: exc.detail[key] for key in I18N_DETAIL_KEYS},
            },
        )
    return None
