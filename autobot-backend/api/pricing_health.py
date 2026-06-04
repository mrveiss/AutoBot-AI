# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Health probe for the pricing refresh subsystem (GH#6480).

Registers under KnownProbes.PRICING. The probe reports:
  - "ok"       — all known providers have a recent successful refresh
  - "degraded" — one or more providers failed their last refresh
  - "down"     — Redis is unreachable or no refresh has run at all
"""

from __future__ import annotations

from fastapi import Request

from api.system_health import ComponentHealth, KnownProbes, register_health_probe

_MAX_STALE_SECONDS = 26 * 60 * 60  # 26 h — 24 h refresh cadence + 2 h grace


@register_health_probe(KnownProbes.PRICING)
async def _pricing_health_probe(request: Request | None) -> ComponentHealth:
    try:
        from datetime import datetime, timezone

        from llm_shared.pricing.redis_store import PricingRedisStore

        store = PricingRedisStore()
        status = await store.get_refresh_status()

        if not status:
            return ComponentHealth(
                name=KnownProbes.PRICING,
                status="degraded",
                detail="No pricing refresh has run yet; using hardcoded fallback table",
            )

        failed = [p for p, s in status.items() if not s.get("success")]
        now = datetime.now(tz=timezone.utc)
        stale = []
        for prov, s in status.items():
            last = s.get("last_refresh_at")
            if last:
                try:
                    age = (now - datetime.fromisoformat(last)).total_seconds()
                    if age > _MAX_STALE_SECONDS:
                        stale.append(prov)
                except ValueError:
                    pass

        probe_status: str
        detail: str
        if failed or stale:
            probe_status = "degraded"
            parts = []
            if failed:
                parts.append(f"failed providers: {failed}")
            if stale:
                parts.append(f"stale providers: {stale}")
            detail = "; ".join(parts)
        else:
            probe_status = "ok"
            detail = f"{len(status)} provider(s) refreshed successfully"

        return ComponentHealth(
            name=KnownProbes.PRICING,
            status=probe_status,
            detail=detail,
            data=status,
        )
    except Exception as exc:
        return ComponentHealth(
            name=KnownProbes.PRICING,
            status="down",
            detail=f"pricing health check error: {exc}",
        )
