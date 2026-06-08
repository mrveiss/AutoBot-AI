# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Adapter API endpoints - Health testing and management for LLM adapters.

Issue #1403: Provides environment test, model listing, and adapter
status endpoints for the formal adapter registry.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from api.schemas_agent import (
    AdapterListResponse,
    AdapterModelsResponse,
    AdapterOverrideClearResponse,
    AdapterOverrideSetResponse,
    AdapterTestResponse,
)
from api.schemas_common import DataResponse
from api.system_health import ComponentHealth, register_health_probe
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from llm_shared.adapters.registry import get_adapter_registry

logger = get_logger(__name__)

router = APIRouter()


@router.get("/", response_model=DataResponse[AdapterListResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_adapters",
    error_code_prefix="ADAPTERS",
)
async def list_adapters(
    current_user: dict = Depends(get_current_user),
):
    """List all registered adapters with status (#1403)."""
    registry = get_adapter_registry()
    adapters = registry.list_adapters()
    return JSONResponse(
        status_code=200,
        content={"adapters": adapters, "total": len(adapters)},
    )


@router.get("/{adapter_type}/test", response_model=DataResponse[AdapterTestResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_adapter_environment",
    error_code_prefix="ADAPTERS",
)
async def test_adapter_environment(
    adapter_type: str,
    current_user: dict = Depends(get_current_user),
):
    """Test a specific adapter's environment (#1403)."""
    registry = get_adapter_registry()
    adapter = registry.get(adapter_type)

    if not adapter:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown adapter type: {adapter_type}",
        )

    result = await adapter.test_environment()
    return JSONResponse(status_code=200, content=result.to_dict())


@router.get("/{adapter_type}/models", response_model=DataResponse[AdapterModelsResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_adapter_models",
    error_code_prefix="ADAPTERS",
)
async def list_adapter_models(
    adapter_type: str,
    current_user: dict = Depends(get_current_user),
):
    """List available models for a specific adapter (#1403)."""
    registry = get_adapter_registry()
    adapter = registry.get(adapter_type)

    if not adapter:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown adapter type: {adapter_type}",
        )

    models = await adapter.list_models()
    return JSONResponse(
        status_code=200,
        content={
            "adapter_type": adapter_type,
            "models": models,
            "total": len(models),
        },
    )


@router.post("/ollama/pull")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="ollama_pull_model",
    error_code_prefix="ADAPTERS",
)
async def ollama_pull_model(
    body: dict,
    current_user: dict = Depends(get_current_user),
):
    """Pull an Ollama model with streaming progress events (#8344).

    Request body: {"model": "llama3.2"}
    Response: newline-delimited JSON stream of Ollama progress events.
    """
    model = body.get("model")
    if not model:
        raise HTTPException(status_code=400, detail="model is required")

    registry = get_adapter_registry()
    adapter = registry.get("ollama")
    if not adapter:
        raise HTTPException(status_code=404, detail="Ollama adapter not registered")

    async def _stream():
        async for event in adapter.pull_model(model):
            yield json.dumps(event) + "\n"

    return StreamingResponse(_stream(), media_type="application/x-ndjson")


@register_health_probe("adapters")
async def probe_adapters(
    request: Request | None = None,
) -> ComponentHealth:
    """Issue #3333: probe registration for adapters module."""
    try:
        registry = get_adapter_registry()
        adapters = registry.list_adapters()
        adapter_count = len(adapters)
        return ComponentHealth(
            name="adapters",
            status="ok" if adapter_count > 0 else "degraded",
            detail=f"{adapter_count} adapters registered",
            data={"adapter_count": adapter_count},
        )
    except Exception as exc:
        return ComponentHealth(
            name="adapters",
            status="down",
            detail=f"probe error: {type(exc).__name__}",
        )


@router.post("/agent/{agent_id}/override", response_model=DataResponse[AdapterOverrideSetResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="set_agent_adapter_override",
    error_code_prefix="ADAPTERS",
)
async def set_agent_adapter_override(
    agent_id: str,
    body: dict,
    current_user: dict = Depends(get_current_user),
):
    """Set per-agent adapter override (#1403)."""
    adapter_type = body.get("adapter_type")
    if not adapter_type:
        raise HTTPException(status_code=400, detail="adapter_type is required")

    registry = get_adapter_registry()
    if not registry.get(adapter_type):
        raise HTTPException(
            status_code=404,
            detail=f"Unknown adapter type: {adapter_type}",
        )

    registry.set_agent_override(agent_id, adapter_type)
    return JSONResponse(
        status_code=200,
        content={
            "agent_id": agent_id,
            "adapter_type": adapter_type,
        },
    )


@router.delete("/agent/{agent_id}/override", response_model=DataResponse[AdapterOverrideClearResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_agent_adapter_override",
    error_code_prefix="ADAPTERS",
)
async def clear_agent_adapter_override(
    agent_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Clear per-agent adapter override (#1403)."""
    registry = get_adapter_registry()
    registry.clear_agent_override(agent_id)
    return JSONResponse(
        status_code=200,
        content={"agent_id": agent_id, "cleared": True},
    )
