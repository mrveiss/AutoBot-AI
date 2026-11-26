# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The context size every caller of the chat model sends (#21878).

Ollama rebuilds a model's runner when a request asks for a different ``num_ctx`` than the loaded one, so a side
call (the RLM evaluator, the verifier, an interpretation pass) that reaches the chat model with its own context
size reloads it at every turn boundary. The same holds for ``num_gpu`` (#22257): on an 8 GB GPU Ollama leaves the
output layer on the CPU unless every layer is asked for. The chat turn sends ``ModelConfig.CHAT_NUM_CTX`` and the
GPU layer count; this is the one rule that
gives every other caller of the same model the same number. A caller of a different model keeps its own.
"""

from __future__ import annotations

import functools
import logging
from contextvars import ContextVar

from autobot_shared.env_utils import env_raw
from autobot_shared.gpu_telemetry import query_nvidia_gpus
from autobot_shared.ssot_constants import ModelConfig
from autobot_shared.verifier_model import model_listed

logger = logging.getLogger(__name__)

CHAT_NUM_GPU_ENV = "AUTOBOT_CHAT_NUM_GPU"

#: The model THIS request's chat turn runs with (a user may select another than the configured default). Ollama keeps
#: that one resident, so it is the one a side call must not reload. A context variable, not a process global: it is
#: set where the turn's request is built and read by the side calls of the same request (the awaited verifier and
#: planner), so a concurrent session never decides another's request (#22258). Unset = no chat turn in this context.
_last_turn_model: ContextVar[str | None] = ContextVar("chat_turn_model", default=None)


def note_chat_turn_model(model: str | None) -> None:
    """Record the model this request's chat turn is running with, so its side calls send the chat's context size too."""
    _last_turn_model.set(model or None)


def sent_num_ctx() -> int:
    """The ``num_ctx`` every chat request sends to Ollama, whichever model it names (#22016).

    The chat payload (``chat_workflow.prompt_window.chat_request_options``) and the prompt budget both read this,
    so the window the budget counts is the window the request carries.
    """
    return ModelConfig.CHAT_NUM_CTX


def is_chat_model(model: str | None) -> bool:
    """Whether *model* is the configured chat model or the one the last chat turn ran with (bare name = ``:latest``)."""
    from autobot_shared.ssot_config import config

    if not model:
        return False
    chats = [name for name in (config.default_llm_model, _last_turn_model.get()) if name]
    return any(model_listed(model, [c]) or model_listed(c, [model]) for c in chats)


def num_ctx_for_model(model: str | None, default: int | None = None) -> int | None:
    """``CHAT_NUM_CTX`` when *model* is a chat model, else *default* (the caller's own context size)."""
    return ModelConfig.CHAT_NUM_CTX if is_chat_model(model) else default


@functools.lru_cache(maxsize=1)
def _host_has_nvidia_gpu() -> bool:
    """Whether nvidia-smi lists a GPU on this host (the signal ``HardwareAccelerationManager`` uses, #620)."""
    return bool(query_nvidia_gpus(("name",)))


def chat_num_gpu() -> int | None:
    """The chat model's ``num_gpu``: ``AUTOBOT_CHAT_NUM_GPU`` when set, else all layers on a GPU host, else None.

    ``off`` or a negative number leaves the option out; an unparseable value is logged and treated as unset (#22257).
    """
    raw = env_raw(CHAT_NUM_GPU_ENV)
    if raw is None:
        return ModelConfig.CHAT_NUM_GPU_ALL_LAYERS if _host_has_nvidia_gpu() else None
    if raw.strip().lower() == "off":
        return None
    try:
        value = int(raw)
    except ValueError:
        logger.warning("%s=%r is not an integer or 'off'; the option is left out", CHAT_NUM_GPU_ENV, raw)
        return None
    return value if value >= 0 else None


def chat_context_options(model: str | None, *, reuses_chat: bool = False) -> dict[str, int]:
    """``num_ctx`` (and ``num_gpu`` when configured) for a request to the chat model, else ``{}``.

    The one rule for request options: every caller of the chat model sends the same dict, or Ollama reloads it.
    *reuses_chat* is a caller that has already decided it is asking the resident chat model (the verifier).
    """
    if not (reuses_chat or is_chat_model(model)):
        return {}
    options = {"num_ctx": ModelConfig.CHAT_NUM_CTX}
    if (num_gpu := chat_num_gpu()) is not None:
        options["num_gpu"] = num_gpu
    return options


#: Per-session thinking preference (the conversation's toggle), kept for the calls of that session that carry no
#: request context (the command-interpretation pass). Bounded: the oldest session is dropped past the cap.
_THINKING_SESSIONS_MAX = 256
_thinking_by_session: dict[str, bool] = {}


def note_session_thinking(session_id: str | None, enabled: bool) -> None:
    """Record the conversation's resolved thinking toggle for *session_id* (#22258)."""
    if not session_id:
        return
    _thinking_by_session.pop(session_id, None)
    _thinking_by_session[session_id] = bool(enabled)
    while len(_thinking_by_session) > _THINKING_SESSIONS_MAX:
        _thinking_by_session.pop(next(iter(_thinking_by_session)))


def session_thinking(session_id: str | None) -> bool:
    """The toggle noted for *session_id*; a session never noted is off, the GUI default."""
    return _thinking_by_session.get(session_id, False) if session_id else False


#: The ``think`` field THIS request's chat turn resolved for its model (capability-checked, toggle applied); ``{}`` when
#: the model has no thinking switch. Side calls on the provider path (the verifier, the planner) send the same one, as
#: they send the chat's ``num_ctx``. A context variable like ``_last_turn_model``: per request, never process-wide.
_last_turn_think: ContextVar[dict[str, bool]] = ContextVar("chat_turn_think", default={})


def note_chat_turn_think(field: dict[str, bool]) -> None:
    """Record the resolved ``think`` field of the chat turn now running in this request (#22258)."""
    _last_turn_think.set(dict(field))


def chat_think_options(model: str | None, *, reuses_chat: bool = False) -> dict[str, bool]:
    """The chat turn's ``think`` field for a provider-path request to the chat model, else ``{}`` (#22258).

    Same gate as ``chat_context_options``: a caller of a different model keeps the model's own default, and
    *reuses_chat* is a caller that has already decided it asks the resident chat model (the verifier).
    """
    return dict(_last_turn_think.get()) if (reuses_chat or is_chat_model(model)) else {}


def chat_think_field(thinking_enabled: bool, supports_thinking: bool) -> dict[str, bool]:
    """Ollama's top-level ``think`` (NOT an ``options`` key): the resolved toggle for a model with the ``thinking``
    capability, else ``{}``. The toggle is already resolved (unset = off), so the UI and the request agree (#22258)."""
    return {"think": bool(thinking_enabled)} if supports_thinking else {}


def interpretation_llm_options(model: str | None) -> dict[str, float | int | None]:
    """The options of a command-interpretation call; the chat model is asked with the chat's options (#21878)."""
    options: dict[str, float | int | None] = {"temperature": 0.7, "top_p": 0.9}
    options.update(chat_context_options(model) or {"num_ctx": ModelConfig.DEFAULT_NUM_CTX})
    return options
