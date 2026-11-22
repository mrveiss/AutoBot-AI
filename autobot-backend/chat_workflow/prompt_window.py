# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The prompt budget measured against the window the request really sends (#22016).

``config/context_windows.yaml`` declares a model's capability (32,768 tokens for the chat model), but the chat
request sends ``num_ctx`` = ``ModelConfig.CHAT_NUM_CTX`` (8,192). Budgeting against the declared figure let the
prompt outgrow what Ollama keeps, and Ollama drops the overflow silently. Here the window is what the request sends,
the system prompt is measured (not a 500-token guess), the reply gets its own reserve, and the YAML
``safety_margin`` applies. Lookups are arithmetic over ``len()``; nothing here does I/O.
"""

from __future__ import annotations

from typing import Any, Dict

from autobot_shared.chat_model_context import num_ctx_for_model
from autobot_shared.logging_manager import get_logger
from chat_workflow import limits
from chat_workflow.llm_provider import configured_provider
from llm_shared.types import ProviderType

logger = get_logger(__name__)


def _sends_chat_num_ctx() -> bool:
    """The chat request carries ``num_ctx`` only when the configured provider is Ollama."""
    try:
        return configured_provider() is ProviderType.OLLAMA
    except ValueError:  # a provider name the registry does not know: not Ollama
        return False


def request_window_tokens(cwm: Any, model_name: str | None) -> int:
    """``num_ctx`` the chat request sends (Ollama chat model); the declared YAML window for anything else."""
    sent = num_ctx_for_model(model_name) if _sends_chat_num_ctx() else None
    return int(sent or cwm.get_adaptive_context_length(model_name))


def output_reserve_tokens(cwm: Any, model_name: str | None) -> int:
    """Tokens the prompt budget keeps free for the reply (2,048 at 8,192).

    The budget reserves it; the chat payload does not yet send it as ``num_predict`` (that is built in
    ``manager._get_llm_request_payload``, which follows once #22012 has merged), so it is not an enforced cap yet.
    """
    window = request_window_tokens(cwm, model_name)
    declared = int(cwm.get_model_info(model_name).get("max_output_tokens", 0) or 0)
    share = int(window * limits.OUTPUT_RESERVE_SHARE)
    return min(declared, share) if declared > 0 else share


def _declared_system_reserve(cwm: Any, model_name: str | None) -> int:
    info = cwm.get_model_info(model_name)
    return int((info.get("message_budget") or {}).get("system_prompt", 0) or 0)


def prompt_budget_tokens(cwm: Any, model_name: str | None = None) -> int:
    """Tokens the prompt may use: window x safety margin, less the reply reserve and the declared system reserve."""
    window = request_window_tokens(cwm, model_name)
    margin = float(cwm.config["token_estimation"].get("safety_margin", 1.0) or 1.0)
    reserved = output_reserve_tokens(cwm, model_name) + _declared_system_reserve(cwm, model_name)
    # Never reserve the window away entirely: a pathological config must still leave a usable budget.
    return max(window // 4, int(window * min(margin, 1.0)) - reserved)


def system_overshoot_tokens(cwm: Any, model_name: str | None, system_prompt: str | None) -> int:
    """Tokens the *measured* system prompt takes beyond the 500-token reserve the budget already holds back."""
    if not system_prompt:
        return 0
    return max(0, cwm.estimate_tokens(system_prompt) - _declared_system_reserve(cwm, model_name))


def measured_prompt_budget(cwm: Any, model_name: str | None, system_prompt: str | None) -> int:
    """``get_prompt_budget`` with the system prompt measured, not assumed (#22016); never below zero."""
    return max(0, cwm.get_prompt_budget(model_name) - system_overshoot_tokens(cwm, model_name, system_prompt))


def estimate_send_tokens(cwm: Any, system_prompt: str | None, prompt: str | None) -> int:
    """Estimated tokens of the system field plus the prompt, as they are sent."""
    return cwm.estimate_tokens(system_prompt or "") + cwm.estimate_tokens(prompt or "")


def send_overflow(model_name: str | None, system_prompt: str | None, prompt: str | None) -> Dict[str, int] | None:
    """``{"estimated", "window"}`` when system+prompt plus the reply reserve exceed the window, else ``None``."""
    from context_window_manager import get_context_window_manager

    cwm = get_context_window_manager()
    window = request_window_tokens(cwm, model_name)
    estimated = estimate_send_tokens(cwm, system_prompt, prompt)
    if estimated + output_reserve_tokens(cwm, model_name) <= window:
        return None
    return {"estimated": estimated, "window": window}


def warn_if_over_window(model_name: str | None, system_prompt: str | None, prompt: str | None) -> bool:
    """The send-point check: log when what is about to be sent cannot fit the window with room to reply."""
    try:
        over = send_overflow(model_name, system_prompt, prompt)
    except Exception as exc:  # noqa: BLE001 -- a check must never cost the user their turn
        logger.warning("[#22016] Send-window check unavailable: %s", type(exc).__name__)
        return False
    if over is not None:
        logger.warning("[#22016] Sending ~%(estimated)d tokens into a %(window)d-token window: input will be cut", over)
    return over is not None


def note_prompt_eval(chunk: Dict[str, Any], model_name: str | None) -> bool:
    """Log when a final stream chunk's ``prompt_eval_count`` reached the window (input was cut).

    Not called from the chat stream yet: the chunk is parsed in ``manager.py`` (follows after #22012).
    """
    used = chunk.get("prompt_eval_count")
    if not chunk.get("done") or not isinstance(used, int):
        return False
    window = int(num_ctx_for_model(model_name) or 0) if _sends_chat_num_ctx() else 0
    at_window = window > 0 and used >= window
    if at_window:
        logger.warning(
            "[#22016] Prompt reached the window (%d of %d tokens): the model may have lost input", used, window
        )
    return at_window
