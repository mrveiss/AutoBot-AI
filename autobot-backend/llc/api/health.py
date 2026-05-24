# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC health probe HTTP endpoint (GH#8259)."""

from fastapi import APIRouter, Request

from api.system_health import ComponentHealth

# Import side-effect: registers the probe with the system-health registry
from llc.health.probe import probe_llc  # noqa: F401

router = APIRouter(prefix="/health", tags=["llc-health"])


@router.get("/probe", response_model=ComponentHealth)
async def get_llc_health_probe(request: Request) -> ComponentHealth:
    """Return the LLC system health probe result.

    Covers heartbeat scheduler uptime, per-agent heartbeat lag,
    budget alert counts, and pending approval staleness.
    """
    return await probe_llc(request)
