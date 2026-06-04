# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Admin API: manual pricing override and refresh status (GH#6480).

Endpoints:
  PUT  /api/admin/pricing/{provider}/{model}  — emergency override
  DELETE /api/admin/pricing/{provider}/{model} — remove override
  GET  /api/admin/pricing/status              — refresh status per provider
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from auth_middleware import get_auth_middleware
from utils.catalog_http_exceptions import raise_auth_error

router = APIRouter(prefix="/admin")


def _require_admin(request: Request) -> bool:
    user_data = get_auth_middleware().get_user_from_request(request)
    if not user_data:
        raise_auth_error("AUTH_0002", "Authentication required")
    if user_data.get("role") != "admin":
        raise_auth_error("AUTH_0003", "Admin permission required")
    return True


class PricingOverrideRequest(BaseModel):
    input_per_1m: float = Field(..., gt=0, description="Input cost per 1M tokens (USD)")
    output_per_1m: float = Field(..., gt=0, description="Output cost per 1M tokens (USD)")
    cache_read_per_1m: float = Field(0.0, ge=0)
    cache_write_per_1m: float = Field(0.0, ge=0)


@router.put("/pricing/{provider}/{model}")
async def override_model_pricing(
    provider: str,
    model: str,
    body: PricingOverrideRequest,
    _admin: bool = Depends(_require_admin),
) -> dict:
    """Write an emergency pricing override directly to Redis."""
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
    )
    store = PricingRedisStore()
    ok = await store.set(pricing)
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
    _admin: bool = Depends(_require_admin),
) -> dict:
    """Remove a pricing override from Redis (next refresh will re-populate)."""
    from llm_shared.pricing.redis_store import PricingRedisStore

    store = PricingRedisStore()
    deleted = await store.delete(provider, model)
    return {"provider": provider, "model": model, "deleted": deleted}


@router.get("/pricing/status")
async def get_pricing_refresh_status(_admin: bool = Depends(_require_admin)) -> dict:
    """Return the last refresh timestamp and success/failure per provider."""
    from llm_shared.pricing.redis_store import PricingRedisStore

    store = PricingRedisStore()
    status = await store.get_refresh_status()
    return {"providers": status}
