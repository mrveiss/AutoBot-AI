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

#: The model the last chat turn ran with (a user may select another than the configured default). Ollama keeps that
#: one resident, so it is the one a side call must not reload; this process-wide mark is set where the turn's request
#: is built.
_last_turn_model: str | None = None


def note_chat_turn_model(model: str | None) -> None:
    """Record the model a chat turn is running with, so its side calls send the chat's context size too."""
    global _last_turn_model
    _last_turn_model = model or None


def is_chat_model(model: str | None) -> bool:
    """Whether *model* is the configured chat model or the one the last chat turn ran with (bare name = ``:latest``)."""
    from autobot_shared.ssot_config import config

    if not model:
        return False
    chats = [name for name in (config.default_llm_model, _last_turn_model) if name]
    return any(model_listed(model, [c]) or model_listed(c, [model]) for c in chats)


def num_ctx_for_model(model: str | None, default: int | None = None) -> int | None:
    """``CHAT_NUM_CTX`` when *model* is a chat model, else *default* (the caller's own context size)."""
    return ModelConfig.CHAT_NUM_CTX if is_chat_model(model) else default


def chat_context_options(model: str | None, *, reuses_chat: bool = False) -> dict[str, int]:
    """``{"num_ctx": CHAT_NUM_CTX}`` for a request to the chat model, else ``{}`` (the one rule for request metadata).

    *reuses_chat* is a caller that has already decided it is asking the resident chat model (the verifier).
    """
    return {"num_ctx": ModelConfig.CHAT_NUM_CTX} if reuses_chat or is_chat_model(model) else {}


def interpretation_llm_options(model: str | None) -> dict[str, float | int | None]:
    """The options of a command-interpretation call; the chat model is asked with the chat's context size (#21878)."""
    return {"temperature": 0.7, "top_p": 0.9, "num_ctx": num_ctx_for_model(model, ModelConfig.DEFAULT_NUM_CTX)}
