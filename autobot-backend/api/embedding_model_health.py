# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Health probe: can the configured embedding model actually embed? (#18834)

Registers under ``KnownProbes.EMBEDDING_MODEL``. Two checks, both named in ``detail``:

* **Identity** -- instant: ``active_embedding_model()`` must be an embedding model by the
  canonical list (``autobot_shared.embedding_model.is_embedding_model_id``). Installs from
  before 2026-10-11 carry the chat model ``phi3:mini`` here (the env template wrote the light
  model), and #15502 keeps a deployed value on every update. The probe says so and names the
  fix: pick an embedding model in SLM Settings > LLM (#19373).
* **One real embedding** -- in the background, never inside the 2 s probe budget. The result
  is cached for ``AUTOBOT_EMBEDDING_PROBE_TTL_SECONDS``; a stale or missing result starts a
  refresh and the probe answers from the last one. A model can pass the identity check and
  still fail to embed (not pulled, server started without embeddings). One background embedding
  is bounded by ``AUTOBOT_EMBEDDING_PROBE_TIMEOUT_SECONDS``; past it the result is "timed out".
  Until the first result lands the probe says "ok" with ``data["embedding_measured"] = False``.

"degraded", not "down": the platform runs; what fails is storing and searching knowledge.
"""

from __future__ import annotations

import asyncio
import time

from fastapi import Request

from api.system_health import ComponentHealth, KnownProbes, register_health_probe
from autobot_shared.embedding_model import active_embedding_model, is_embedding_model_id
from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

EMBEDDING_PROBE_TTL_S = env_int_clamped("AUTOBOT_EMBEDDING_PROBE_TTL_SECONDS", 300, min_v=10, max_v=86400)
EMBEDDING_PROBE_TIMEOUT_S = env_int_clamped("AUTOBOT_EMBEDDING_PROBE_TIMEOUT_SECONDS", 60, min_v=1, max_v=600)
_FIX = "pick an embedding model in SLM Settings > LLM (#19373)"
_NOT_MEASURED = "identity checked; test embedding not yet measured (runs in the background)"
_TIMED_OUT = "timed out"

# model -> (monotonic time measured, error or None). One entry per model, so a switch re-probes.
_last_probe: dict[str, tuple[float, str | None]] = {}
_refreshing: set[str] = set()
# Strong references to in-flight refreshes: the loop only keeps weak ones, so an unreferenced
# task can be garbage-collected mid-run.
_refresh_tasks: set[asyncio.Task] = set()


async def probe_one_embedding(model: str) -> str | None:
    """Embed a fixed string with *model*; return None on success, else the reason."""
    from services.npu_client import generate_embedding_with_fallback

    try:
        vector = await generate_embedding_with_fallback("embedding model probe", model_name=model)
    except Exception as exc:  # noqa: BLE001 - the reason is the result
        logger.warning("embedding probe of model %r failed", model, exc_info=True)
        return f"{type(exc).__name__}"
    return None if vector else "no vector returned"


async def _refresh(model: str) -> None:
    try:
        try:
            error = await asyncio.wait_for(probe_one_embedding(model), timeout=EMBEDDING_PROBE_TIMEOUT_S)
        except asyncio.TimeoutError:
            error = _TIMED_OUT
        _last_probe[model] = (time.monotonic(), error)
    finally:
        _refreshing.discard(model)


def _schedule_refresh(model: str) -> None:
    measured = _last_probe.get(model)
    if model in _refreshing or (measured and time.monotonic() - measured[0] < EMBEDDING_PROBE_TTL_S):
        return
    _refreshing.add(model)
    task = asyncio.get_running_loop().create_task(_refresh(model))
    _refresh_tasks.add(task)
    task.add_done_callback(_refresh_tasks.discard)


@register_health_probe(KnownProbes.EMBEDDING_MODEL)
async def _embedding_model_health_probe(request: Request | None = None) -> ComponentHealth:
    model = active_embedding_model()
    data: dict = {"embedding_model": model}
    if not is_embedding_model_id(model):
        return ComponentHealth(
            name=KnownProbes.EMBEDDING_MODEL,
            status="degraded",
            detail=f"configured embedding model '{model}' is not an embedding model -- {_FIX}",
            data=data,
        )
    _schedule_refresh(model)
    measured = _last_probe.get(model)
    data["embedding_measured"] = measured is not None
    if measured and measured[1] is not None:
        return ComponentHealth(
            name=KnownProbes.EMBEDDING_MODEL,
            status="degraded",
            detail=f"embedding model '{model}' could not embed ({measured[1]}) -- {_FIX}",
            data=data,
        )
    detail = None if measured else _NOT_MEASURED
    return ComponentHealth(name=KnownProbes.EMBEDDING_MODEL, status="ok", detail=detail, data=data)
