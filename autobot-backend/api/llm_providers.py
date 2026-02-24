# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Provider Switching API endpoints (Issue #536).

Provides runtime provider switching, provider listing, and per-provider testing.
"""

import logging

from auth_middleware import check_admin_permission, get_current_user
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from utils.advanced_cache_manager import cache_response

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_llm_interface():
    """Get LLMInterface instance."""
    from llm_interface_pkg.interface import LLMInterface

    return LLMInterface()


@router.post("/switch")
async def switch_llm_provider(
    switch_data: dict,
    admin_check: bool = Depends(check_admin_permission),
):
    """Switch active LLM provider at runtime.

    Body: {"provider": "openai", "model": "gpt-4", "validate": true}
    """
    provider = switch_data.get("provider")
    if not provider:
        raise HTTPException(status_code=400, detail="provider is required")
    llm = _get_llm_interface()
    result = await llm.switch_provider(
        provider,
        model=switch_data.get("model", ""),
        validate=switch_data.get("validate", False),
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return JSONResponse(status_code=200, content=result)


@router.get("/providers")
@cache_response(cache_key="llm_providers_list", ttl=30)
async def list_llm_providers(
    current_user: dict = Depends(get_current_user),
):
    """List all configured LLM providers with status."""
    llm = _get_llm_interface()
    statuses = await llm.get_all_provider_status()
    return JSONResponse(
        status_code=200,
        content={"active_provider": llm._active_provider, "providers": statuses},
    )


@router.post("/providers/{provider_name}/test")
async def test_llm_provider(
    provider_name: str,
    current_user: dict = Depends(get_current_user),
):
    """Test a specific LLM provider connection."""
    llm = _get_llm_interface()
    if provider_name not in llm.provider_routing:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown provider: {provider_name}",
        )
    is_healthy, error = await llm._is_provider_healthy(provider_name)
    return JSONResponse(
        status_code=200,
        content={"provider": provider_name, "available": is_healthy, "error": error},
    )
