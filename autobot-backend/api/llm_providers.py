# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Provider Switching API endpoints (Issue #536).

Provides runtime provider switching, provider listing, and per-provider testing.
"""

import json
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from api.schemas_common import DataResponse
from api.schemas_system import LLMProviderListData, LLMProviderSwitchData, LLMProviderTestData
from auth_middleware import check_admin_permission, get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from llm_shared.fallback_chain import get_fallback_chain_manager
from services.llm_service import get_llm_service
from utils.advanced_cache_manager import cache_response

logger = get_logger(__name__)

router = APIRouter()


@router.post("/switch", response_model=DataResponse[LLMProviderSwitchData])
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


@router.get("/providers", response_model=DataResponse[LLMProviderListData])
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


@router.post("/providers/{provider_name}/test", response_model=DataResponse[LLMProviderTestData])
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
    llm = get_llm_service()
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


@router.get("/fallback-status")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_fallback_status",
    error_code_prefix="LLM_PROVIDERS",
)
async def get_fallback_status(
    current_user: dict = Depends(get_current_user),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get LLM fallback chain status (GH#8998 - MVA-2999).

    Returns:
        - configured_chains: List of configured fallback chains
        - active_fallbacks: List of currently active fallback events
    """
    # Get configured fallback chains
    fallback_manager = get_fallback_chain_manager()
    chains_dict = fallback_manager.list_chains()

    configured_chains = [
        {
            "primary_model": primary,
            "fallback_chain": " → ".join(fallbacks),
            "provider": "multi",  # Can be multi-provider
        }
        for primary, fallbacks in chains_dict.items()
    ]

    # Get active fallbacks from Redis
    active_fallbacks: List[Dict[str, Any]] = []
    try:
        redis_client = get_redis_client(database="main")
        # Scan for all active fallback keys
        cursor = 0
        while True:
            cursor, keys = redis_client.scan(
                cursor,
                match="llm:fallback:active:*",
                count=100,
            )

            for key in keys:
                try:
                    data = redis_client.get(key)
                    if data:
                        event = json.loads(data)
                        active_fallbacks.append(event)
                except Exception as exc:
                    logger.warning(
                        "Failed to parse fallback event from key %s: %s",
                        key,
                        exc,
                    )

            if cursor == 0:
                break

    except Exception as exc:
        logger.warning(
            "Failed to fetch active fallbacks from Redis: %s",
            exc,
            exc_info=True,
        )

    return JSONResponse(
        status_code=200,
        content={
            "configured_chains": configured_chains,
            "active_fallbacks": active_fallbacks,
        },
    )
