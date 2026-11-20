# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The context size every caller of the chat model sends (#21878).

Ollama rebuilds a model's runner when a request asks for a different ``num_ctx`` than the loaded one, so a side
call (the RLM evaluator, the verifier, an interpretation pass) that reaches the chat model with its own context
size reloads it at every turn boundary. The chat turn sends ``ModelConfig.CHAT_NUM_CTX``; this is the one rule that
gives every other caller of the same model the same number. A caller of a different model keeps its own.
"""

from __future__ import annotations

from autobot_shared.ssot_constants import ModelConfig
from autobot_shared.verifier_model import model_listed


def is_chat_model(model: str | None) -> bool:
    """Whether *model* names the configured chat model (a bare name means its ``:latest`` tag)."""
    from autobot_shared.ssot_config import config

    chat = config.default_llm_model
    return bool(model and chat and (model_listed(model, [chat]) or model_listed(chat, [model])))


def num_ctx_for_model(model: str | None, default: int | None = None) -> int | None:
    """``CHAT_NUM_CTX`` when *model* is the chat model, else *default* (the caller's own context size)."""
    return ModelConfig.CHAT_NUM_CTX if is_chat_model(model) else default
