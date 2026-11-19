# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Health probe: is the configured pre-action verifier model installed? (#21844)

Registers under ``KnownProbes.VERIFIER_MODEL``. "degraded", not "down": the platform runs and the verifier falls back
to the provider default model, but the configured one is not what answers. The reading comes from the provider's
own model list (``autobot_shared.verifier_model``), cached for its TTL; a list that cannot be read is "ok" with
``data["verifier_model_checked"] = False``, since nothing proves the model missing. A disabled verifier
(``VERIFIER_ENABLED=0``) is ``not_applicable``: it needs no model.
"""

from __future__ import annotations

from fastapi import Request

from api.system_health import ComponentHealth, KnownProbes, register_health_probe
from autobot_shared import pre_action_verifier_guard
from autobot_shared.verifier_model import check_verifier_model

_FIX = "pull the model on the Ollama host or change AUTOBOT_VERIFIER_MODEL"


@register_health_probe(KnownProbes.VERIFIER_MODEL)
async def _verifier_model_health_probe(request: Request | None = None) -> ComponentHealth:
    if not pre_action_verifier_guard.VERIFIER_ENABLED:
        detail = "pre-action verifier disabled (VERIFIER_ENABLED=0); its model is not needed"
        return ComponentHealth(name=KnownProbes.VERIFIER_MODEL, status="not_applicable", detail=detail)
    model, available = await check_verifier_model()
    data = {"verifier_model": model, "verifier_model_checked": available is not None}
    if available is False:
        detail = f"verifier model '{model}' is not installed; verifier calls use the provider default -- {_FIX}"
        return ComponentHealth(name=KnownProbes.VERIFIER_MODEL, status="degraded", detail=detail, data=data)
    return ComponentHealth(name=KnownProbes.VERIFIER_MODEL, status="ok", data=data)
