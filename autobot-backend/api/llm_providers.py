# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Provider Switching API endpoints (Issue #536).

Provides runtime provider switching, provider listing, and per-provider testing.
"""

import logging
from autobot_shared.logging_manager import get_logger

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from api.schemas_common import DataResponse
from auth_middleware import check_admin_permission, get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from services.llm_service import get_llm_service
from utils.advanced_cache_manager import cache_response

logger = get_logger(__name__)

router = APIRouter()


def _get_llm_interface():
    """Return the LLMService singleton (#3185).

    Name retained for backwards compatibility — LLMService exposes
    ``provider_routing`` and ``is_provider_healthy`` matching the
    LLMInterface surface this module previously used.
    """
    from services.llm_service import get_llm_service

    return get_llm_service()


@router.post("/switch", response_model=DataResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="switch_llm_provider",
    error_code_prefix="LLM_PROVIDERS",
)
async def switch_llm_provider(
    switch_data: dict,
    admin_check: bool = Depends(check_admin_permission),
):
    """Switch active LLM provider at runtime.

    Body: {"provider": "openai", "model": "<model-name>", "validate": true}
    See ModelConstants.DEFAULT_OPENAI_MODEL for the default OpenAI model.
    """
    provider = switch_data.get("provider")
    if not provider:
        raise HTTPException(status_code=400, detail="provider is required")
    llm = get_llm_service()
    result = await llm.switch_provider(
        provider,
        model=switch_data.get("model", ""),
        validate=switch_data.get("validate", False),
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return JSONResponse(status_code=200, content=result)


@router.get("/providers", response_model=DataResponse)
@cache_response(cache_key="llm_providers_list", ttl=30)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_llm_providers",
    error_code_prefix="LLM_PROVIDERS",
)
async def list_llm_providers(
    current_user: dict = Depends(get_current_user),
):
    """List all configured LLM providers with status."""
    llm = get_llm_service()
    statuses = await llm.get_all_provider_status()
    return JSONResponse(
        status_code=200,
        content={"active_provider": llm._active_provider, "providers": statuses},
    )


@router.post("/providers/{provider_name}/test", response_model=DataResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_llm_provider",
    error_code_prefix="LLM_PROVIDERS",
)
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
    is_healthy, error = await llm.is_provider_healthy(provider_name)
    return JSONResponse(
        status_code=200,
        content={"provider": provider_name, "available": is_healthy, "error": error},
    )
