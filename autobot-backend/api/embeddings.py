# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Embeddings API Router

Provides endpoints for configuring and managing embedding models and providers.
Handles vector storage configuration and embedding model selection.
"""

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from api.schemas_common import DataResponse
from api.schemas_embeddings import EmbeddingModelsData
from api.schemas_knowledge import (
    EmbeddingRefreshData,
    EmbeddingSettingsData,
    EmbeddingStatusData,
    EmbeddingUpdate,
)
from auth_middleware import check_admin_permission, get_current_user
from autobot_shared.embedding_model import active_embedding_model
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import DEFAULT_EMBEDDING_MODEL
from config import unified_config_manager
from services.config_service import ConfigService
from services.embedding_options import embedding_model_options

logger = get_logger(__name__)

router = APIRouter(tags=["embeddings"])


@router.get("/settings", response_model=DataResponse[EmbeddingSettingsData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_embedding_settings",
    error_code_prefix="EMBEDDINGS",
)
async def get_embedding_settings(
    current_user: dict = Depends(get_current_user),
):
    """Get current embedding configuration settings.

    Issue #744: Requires authenticated user.
    """
    try:
        # Get embedding configuration from unified config manager
        embedding_config = unified_config_manager.get_nested("backend.llm.unified.embedding", {})

        if not embedding_config:
            # Return default configuration if none exists
            from autobot_shared.ssot_config import config

            embedding_config = {
                "provider": "ollama",
                "providers": {
                    "ollama": {
                        "endpoint": f"{config.ollama_url}/api/embeddings",
                        "selected_model": DEFAULT_EMBEDDING_MODEL,
                        "models": [DEFAULT_EMBEDDING_MODEL],
                    }
                },
            }
        # #19377: the model actually in use is the resolver's, never this file's copy, which
        # no embedding call reads -- reporting the file's value showed a model that was not used.
        provider = embedding_config.get("provider", "ollama")
        embedding_config.setdefault("providers", {}).setdefault(provider, {})["selected_model"] = (
            await asyncio.to_thread(active_embedding_model)
        )  # may read Redis; off the event loop

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "embedding_config": embedding_config,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
        )

    except Exception as e:
        logger.error("Failed to get embedding settings: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get embedding settings")


@router.put(
    "/settings",
    responses={
        409: {
            "description": (
                "Always: the embedding model is changed through the embedding-model switch "
                "(#19379), which re-indexes the knowledge base, never through this endpoint."
            )
        }
    },
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_embedding_settings",
    error_code_prefix="EMBEDDINGS",
)
async def update_embedding_settings(
    update: EmbeddingUpdate,
    admin_check: bool = Depends(check_admin_permission),
):
    """Update embedding configuration settings.

    Issue #744: Requires admin authentication.
    """
    # #19377: this used to write a settings.json block that no embedding call reads, report
    # success, and change nothing. Changing the model re-indexes the knowledge base, so it goes
    # through the switch flow (#19379), not through this endpoint.
    active = await asyncio.to_thread(active_embedding_model)  # may read Redis; off the event loop
    return JSONResponse(
        status_code=409,
        content={
            "status": "error",
            "message": (
                f"The embedding model is not changed here. The active model is "
                f"'{active}'; switching it rebuilds the knowledge-base index "
                f"and is done through the embedding-model switch (#19379)."
            ),
            "requested": {"provider": update.provider, "selected_model": update.selected_model},
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        },
    )


@router.get("/models", response_model=DataResponse[EmbeddingModelsData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_available_embedding_models",
    error_code_prefix="EMBEDDINGS",
)
async def get_available_embedding_models(
    current_user: dict = Depends(get_current_user),
):
    """The embedding models the user can switch to right now, with the active one marked (#19378).

    This used to return the provider lists saved in settings.json, which nothing keeps current;
    ``GET /api/llm/embedding/models`` (its own name patterns) now redirects here.
    """
    return DataResponse(data=EmbeddingModelsData(**await embedding_model_options()))


@router.post("/providers/{provider_name}/refresh-models", response_model=DataResponse[EmbeddingRefreshData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="refresh_embedding_models",
    error_code_prefix="EMBEDDINGS",
)
async def refresh_embedding_models(
    provider_name: str,
    admin_check: bool = Depends(check_admin_permission),
):
    """Refresh available models for a specific embedding provider.

    Issue #744: Requires admin authentication.
    """
    try:
        if provider_name == "ollama":
            # For Ollama, we can check available embedding models
            # This is a placeholder - in real implementation, you'd query Ollama API
            embedding_models = [
                "nomic-embed-text:latest",
                "mxbai-embed-large:latest",
                "snowflake-arctic-embed:latest",
            ]

            # Update the configuration with available models
            unified_config_manager.set_nested(
                f"backend.llm.unified.embedding.providers.{provider_name}.models",
                embedding_models,
            )
            unified_config_manager.save_settings()
            ConfigService.clear_cache()

            logger.info("Refreshed embedding models for %s", provider_name)

            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "message": f"Models refreshed for {provider_name}",
                    "models": embedding_models,
                    "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                },
            )
        else:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": (f"Model refresh not implemented for provider: {provider_name}"),
                },
            )

    except Exception as e:
        logger.error("Failed to refresh embedding models for %s: %s", provider_name, e)
        raise HTTPException(status_code=500, detail="Failed to refresh embedding models")


@router.get("/status", response_model=DataResponse[EmbeddingStatusData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_embedding_status",
    error_code_prefix="EMBEDDINGS",
)
async def get_embedding_status(
    current_user: dict = Depends(get_current_user),
):
    """Get current embedding system status.

    Issue #744: Requires authenticated user.
    """
    try:
        embedding_config = unified_config_manager.get_nested("backend.llm.unified.embedding", {})
        current_provider = embedding_config.get("provider", "ollama")

        provider_config = embedding_config.get("providers", {}).get(current_provider, {})
        # #19377: the model in use, not the file's copy; it may read Redis, so off the event loop
        selected_model = await asyncio.to_thread(active_embedding_model)
        endpoint = provider_config.get("endpoint", "")

        # Basic status check
        status = {
            "configured": bool(selected_model and endpoint),
            "provider": current_provider,
            "model": selected_model,
            "endpoint": endpoint,
            "last_check": datetime.now(tz=timezone.utc).isoformat(),
        }

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "embedding_status": status,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
        )

    except Exception as e:
        logger.error("Failed to get embedding status: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get embedding status")
