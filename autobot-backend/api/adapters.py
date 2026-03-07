# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Adapter API endpoints - Health testing and management for LLM adapters.

Issue #1403: Provides environment test, model listing, and adapter
status endpoints for the formal adapter registry.
"""

import logging

from auth_middleware import get_current_user
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from llm_interface_pkg.adapters.registry import get_adapter_registry

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/")
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


@router.get("/{adapter_type}/test")
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


@router.get("/{adapter_type}/models")
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


@router.get("/health")
async def test_all_adapters(
    current_user: dict = Depends(get_current_user),
):
    """Test all registered adapters in parallel (#1403)."""
    registry = get_adapter_registry()
    results = await registry.test_all()
    return JSONResponse(
        status_code=200,
        content={name: result.to_dict() for name, result in results.items()},
    )


@router.post("/agent/{agent_id}/override")
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


@router.delete("/agent/{agent_id}/override")
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
