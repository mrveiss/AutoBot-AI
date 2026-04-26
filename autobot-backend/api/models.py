# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Models API — dynamic LLM model list from the live system (#3280).

Exposes GET /api/models/available which returns models from all configured
providers with provider, context-window, and capability metadata.
Results are cached for 60 seconds to avoid latency on every dropdown open.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from api.schemas_common import DataResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_available_models",
    error_code_prefix="MODELS",
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_available_models",
    error_code_prefix="MODELS",
)
@router.get("/available", response_model=DataResponse)
async def get_available_models(
    current_user: dict = Depends(get_current_user),
):
    """Return available LLM models from all configured providers.

    Results include provider, context_window, capabilities, and availability.
    Cached for 60 seconds in Redis to avoid latency on dropdown opens.

    Issue #3280: replaces the hardcoded empty model list in agent_config.py.
    """
    try:
        from services.model_manager_service import get_available_models as _fetch

        result = await _fetch()
        return JSONResponse(status_code=200, content=result)
    except Exception as exc:
        logger.error("Failed to fetch available models: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch available models")
