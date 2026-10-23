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
  still fail to embed (not pulled, server started without embeddings).

"degraded", not "down": the platform runs; what fails is storing and searching knowledge.
"""

from __future__ import annotations

import asyncio
import time

from fastapi import Request

from api.system_health import ComponentHealth, KnownProbes, register_health_probe
from autobot_shared.embedding_model import active_embedding_model, is_embedding_model_id
from autobot_shared.env_utils import env_int_clamped

EMBEDDING_PROBE_TTL_S = env_int_clamped("AUTOBOT_EMBEDDING_PROBE_TTL_SECONDS", 300, min_v=10)
_FIX = "pick an embedding model in SLM Settings > LLM (#19373)"

# model -> (monotonic time measured, error or None). One entry per model, so a switch re-probes.
_last_probe: dict[str, tuple[float, str | None]] = {}
_refreshing: set[str] = set()


async def probe_one_embedding(model: str) -> str | None:
    """Embed a fixed string with *model*; return None on success, else the reason."""
    from services.npu_client import generate_embedding_with_fallback

    try:
        vector = await generate_embedding_with_fallback("embedding model probe", model_name=model)
    except Exception as exc:  # noqa: BLE001 - the reason is the result
        return f"{type(exc).__name__}"
    return None if vector else "no vector returned"


async def _refresh(model: str) -> None:
    try:
        _last_probe[model] = (time.monotonic(), await probe_one_embedding(model))
    finally:
        _refreshing.discard(model)


def _schedule_refresh(model: str) -> None:
    measured = _last_probe.get(model)
    if model in _refreshing or (measured and time.monotonic() - measured[0] < EMBEDDING_PROBE_TTL_S):
        return
    _refreshing.add(model)
    asyncio.get_running_loop().create_task(_refresh(model))


@register_health_probe(KnownProbes.EMBEDDING_MODEL)
async def _embedding_model_health_probe(request: Request | None = None) -> ComponentHealth:
    model = active_embedding_model()
    data = {"embedding_model": model}
    if not is_embedding_model_id(model):
        return ComponentHealth(
            name=KnownProbes.EMBEDDING_MODEL,
            status="degraded",
            detail=f"configured embedding model '{model}' is not an embedding model -- {_FIX}",
            data=data,
        )
    _schedule_refresh(model)
    measured = _last_probe.get(model)
    if measured and measured[1] is not None:
        return ComponentHealth(
            name=KnownProbes.EMBEDDING_MODEL,
            status="degraded",
            detail=f"embedding model '{model}' could not embed ({measured[1]}) -- {_FIX}",
            data=data,
        )
    return ComponentHealth(name=KnownProbes.EMBEDDING_MODEL, status="ok", detail=None, data=data)
