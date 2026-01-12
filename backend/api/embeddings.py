# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Embeddings API Router

Provides endpoints for configuring and managing embedding models and providers.
Handles vector storage configuration and embedding model selection.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.services.config_service import ConfigService
from src.config import unified_config_manager
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/embeddings", tags=["embeddings"])


class EmbeddingProviderConfig(BaseModel):
    """Embedding provider configuration model"""

    provider: str
    endpoint: str
    selected_model: str
    models: List[str] = []


class EmbeddingConfig(BaseModel):
    """Embedding configuration model"""

    provider: str
    providers: Dict[str, EmbeddingProviderConfig]


class EmbeddingUpdate(BaseModel):
    """Embedding configuration update request"""

    provider: str
    selected_model: str
    endpoint: Optional[str] = None


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_embedding_settings",
    error_code_prefix="EMBEDDINGS",
)
@router.get("/settings")
async def get_embedding_settings():
    """Get current embedding configuration settings"""
    try:
        # Get embedding configuration from unified config manager
        embedding_config = unified_config_manager.get_nested(
            "backend.llm.unified.embedding", {}
        )

        if not embedding_config:
            # Return default configuration if none exists
            embedding_config = {
                "provider": "ollama",
                "providers": {
                    "ollama": {
                        "endpoint": "ServiceURLs.OLLAMA_LOCAL/api/embeddings",
                        "selected_model": "nomic-embed-text:latest",
                        "models": ["nomic-embed-text:latest"],
                    }
                },
            }

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "embedding_config": embedding_config,
                "timestamp": datetime.now().isoformat(),
            },
        )

    except Exception as e:
        logger.error("Failed to get embedding settings: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to get embedding settings: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_embedding_settings",
    error_code_prefix="EMBEDDINGS",
)
@router.put("/settings")
async def update_embedding_settings(update: EmbeddingUpdate):
    """Update embedding configuration settings"""
    try:
        # Update the embedding configuration
        unified_config_manager.set_nested(
            "backend.llm.unified.embedding.provider", update.provider
        )
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

        logger.info(
            f"Updated embedding configuration: provider={update.provider}, model={update.selected_model}"
        )

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
                "timestamp": datetime.now().isoformat(),
            },
        )

    except Exception as e:
        logger.error("Failed to update embedding settings: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to update embedding settings: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_available_embedding_models",
    error_code_prefix="EMBEDDINGS",
)
@router.get("/models")
async def get_available_embedding_models():
    """Get available embedding models from all providers"""
    try:
        embedding_config = unified_config_manager.get_nested(
            "backend.llm.unified.embedding", {}
        )
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
                "timestamp": datetime.now().isoformat(),
            },
        )

    except Exception as e:
        logger.error("Failed to get embedding models: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to get embedding models: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="refresh_embedding_models",
    error_code_prefix="EMBEDDINGS",
)
@router.post("/providers/{provider_name}/refresh-models")
async def refresh_embedding_models(provider_name: str):
    """Refresh available models for a specific embedding provider"""
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
                    "timestamp": datetime.now().isoformat(),
                },
            )
        else:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": (
                        f"Model refresh not implemented for provider: {provider_name}"
                    ),
                },
            )

    except Exception as e:
        logger.error("Failed to refresh embedding models for %s: %s", provider_name, e)
        raise HTTPException(
            status_code=500, detail=f"Failed to refresh embedding models: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_embedding_status",
    error_code_prefix="EMBEDDINGS",
)
@router.get("/status")
async def get_embedding_status():
    """Get current embedding system status"""
    try:
        embedding_config = unified_config_manager.get_nested(
            "backend.llm.unified.embedding", {}
        )
        current_provider = embedding_config.get("provider", "ollama")

        provider_config = embedding_config.get("providers", {}).get(
            current_provider, {}
        )
        selected_model = provider_config.get("selected_model", "")
        endpoint = provider_config.get("endpoint", "")

        # Basic status check
        status = {
            "configured": bool(selected_model and endpoint),
            "provider": current_provider,
            "model": selected_model,
            "endpoint": endpoint,
            "last_check": datetime.now().isoformat(),
        }

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "embedding_status": status,
                "timestamp": datetime.now().isoformat(),
            },
        )

    except Exception as e:
        logger.error("Failed to get embedding status: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to get embedding status: {str(e)}"
        )
