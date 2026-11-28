# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The LLM models AutoBot can use, as self-model ``model`` entities (#22277).

``ProviderRegistry`` is the one source of which providers exist and whether they answer; each provider's own
``list_models`` is the one source of which models it serves. A model is ``probed_ok`` when its provider's
availability check passed on this push and ``probed_failed`` when it did not. The model list of a provider that
cannot be listed is left out, so the model becomes ``absent`` rather than keeping a claim nobody re-checked.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from llm_shared import get_provider_registry
from tools.tool_records import location_host

logger = get_logger(__name__)

MODEL_KIND = "model"
_SERVICE = "service"
_NAME_MAX = 255  # the SLM entity name column
_PROBE = "provider_availability"


def _model_observation(provider: str, model: str, available: bool, probed_at: str, is_local: bool) -> Dict[str, Any]:
    """One model as an observation under the provider that serves it."""
    return {
        "kind": MODEL_KIND,
        "name": model[:_NAME_MAX],
        "status": "probed_ok" if available else "probed_failed",
        "parent": {"kind": _SERVICE, "name": provider},
        "node_id": location_host(provider),
        "attrs": {"provider": provider, "is_local": is_local, "probe": _PROBE, "probed_at": probed_at},
    }


async def model_observations() -> List[Dict[str, Any]]:
    """Every model every registered provider lists, probed by that provider's availability check."""
    registry = get_provider_registry()
    availability = await registry.health_check_all()
    probed_at = datetime.now(timezone.utc).isoformat()
    facts = registry.get_provider_facts()
    out: List[Dict[str, Any]] = []
    for name, available in sorted(availability.items()):
        provider = registry.get_provider_by_name(name)
        try:
            models = await provider.list_models()
        except Exception as exc:  # noqa: BLE001 - one provider's failed listing must not hide the others' models
            logger.warning("self-model: %s could not list its models, leaving them out: %s", name, exc)
            continue
        is_local = bool(facts[name].is_local) if name in facts else False
        out.extend(_model_observation(name, m, available, probed_at, is_local) for m in sorted(set(models)))
    return out
