# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Admin API: manual pricing override, refresh status, and refresh-now (GH#6480, #16231).

Endpoints:
  PUT  /api/admin/pricing/{provider}/{model}  — emergency override
  DELETE /api/admin/pricing/{provider}/{model} — remove override
  GET  /api/admin/pricing/status              — refresh status per provider
  POST /api/admin/pricing/refresh             — refresh now, on demand (#16231)
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from api.schemas_pricing import PricingOverrideRequest
from auth_rbac import require_role

router = APIRouter(prefix="/admin")


@router.put("/pricing/{provider}/{model}")
async def override_model_pricing(
    provider: str,
    model: str,
    body: PricingOverrideRequest,
    _admin: bool = Depends(require_role("admin", "superadmin")),
) -> dict:
    """Store an emergency pricing override; it outranks the refreshed price until removed."""
    from autobot_shared.logging_manager import get_logger
    from llm_shared.pricing.redis_store import PricingRedisStore
    from llm_shared.pricing.sources import ModelPricing

    logger = get_logger(__name__)

    pricing = ModelPricing(
        provider=provider,
        model_id=model,
        input_per_1m=body.input_per_1m,
        output_per_1m=body.output_per_1m,
        cache_read_per_1m=body.cache_read_per_1m,
        cache_write_per_1m=body.cache_write_per_1m,
        updated_at=datetime.now(tz=timezone.utc),
        source="override",
    )
    store = PricingRedisStore()
    ok = await store.set_override(pricing)
    logger.info(
        "admin pricing override: provider=%s model=%s input=%.4f output=%.4f success=%s",
        provider,
        model,
        body.input_per_1m,
        body.output_per_1m,
        ok,
    )
    return {
        "provider": provider,
        "model": model,
        "stored": ok,
        "pricing": pricing.to_dict(),
    }


@router.delete("/pricing/{provider}/{model}")
async def delete_model_pricing_override(
    provider: str,
    model: str,
    _admin: bool = Depends(require_role("admin", "superadmin")),
) -> dict:
    """Remove a pricing override; the refreshed price applies again."""
    from llm_shared.pricing.redis_store import PricingRedisStore

    store = PricingRedisStore()
    deleted = await store.delete_override(model)
    return {"provider": provider, "model": model, "deleted": deleted}


@router.get("/pricing/status")
async def get_pricing_refresh_status(_admin: bool = Depends(require_role("admin", "superadmin"))) -> dict:
    """Return the last refresh timestamp and success/failure per provider."""
    from llm_shared.pricing.redis_store import PricingRedisStore

    store = PricingRedisStore()
    status = await store.get_refresh_status()
    return {"providers": status}


@router.post("/pricing/refresh")
async def refresh_pricing_now(_admin: bool = Depends(require_role("admin", "superadmin"))) -> dict:
    """Refresh pricing on demand and report the per-source result (#16231)."""
    from services.pricing_refresh import refresh_all

    return await refresh_all()
