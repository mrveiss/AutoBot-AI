# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Embeddings API Router

Provides endpoints for configuring and managing embedding models and providers.
Handles vector storage configuration and embedding model selection.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from api.schemas_common import DataResponse
from api.schemas_knowledge import (
    EmbeddingModelsData,
    EmbeddingRefreshData,
    EmbeddingSettingsData,
    EmbeddingStatusData,
    EmbeddingUpdate,
    EmbeddingUpdateData,
)
from auth_middleware import check_admin_permission, get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import DEFAULT_EMBEDDING_MODEL
from config import unified_config_manager
from services.config_service import ConfigService

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


@router.put("/settings", response_model=DataResponse[EmbeddingUpdateData])
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
    try:
        # Update the embedding configuration
        unified_config_manager.set_nested("backend.llm.unified.embedding.provider", update.provider)
        unified_config_manager.set_nested(
            f"backend.llm.unified.embedding.providers.{update.provider}.selected_model",
            update.selected_model,
        )

        if update.endpoint:
            unified_config_manager.set_nested(
                f"backend.llm.unified.embedding.providers.{update.provider}.endpoint",
                update.endpoint,
            )

        # Save configuration and clear cache
        unified_config_manager.save_settings()
        ConfigService.clear_cache()

        logger.info(f"Updated embedding configuration: provider={update.provider}, model={update.selected_model}")

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Embedding configuration updated successfully",
                "updated_config": {
                    "provider": update.provider,
                    "selected_model": update.selected_model,
                    "endpoint": update.endpoint,
                },
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
        )

    except Exception as e:
        logger.error("Failed to update embedding settings: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update embedding settings")


@router.get("/models", response_model=DataResponse[EmbeddingModelsData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_available_embedding_models",
    error_code_prefix="EMBEDDINGS",
)
async def get_available_embedding_models(
    current_user: dict = Depends(get_current_user),
):
    """Get available embedding models from all providers.

    Issue #744: Requires authenticated user.
    """
    try:
        embedding_config = unified_config_manager.get_nested("backend.llm.unified.embedding", {})
        providers = embedding_config.get("providers", {})

        available_models = {}

        for provider_name, provider_config in providers.items():
            models = provider_config.get("models", [])
            selected_model = provider_config.get("selected_model", "")
            endpoint = provider_config.get("endpoint", "")

            available_models[provider_name] = {
                "models": models,
                "selected_model": selected_model,
                "endpoint": endpoint,
                "status": "available" if models else "no_models",
            }

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "providers": available_models,
                "current_provider": embedding_config.get("provider", "ollama"),
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
        )

    except Exception as e:
        logger.error("Failed to get embedding models: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get embedding models")


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
        selected_model = provider_config.get("selected_model", "")
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
