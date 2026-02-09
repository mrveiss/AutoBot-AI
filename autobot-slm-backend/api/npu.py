# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
NPU Worker API Routes (Issue #255 - NPU Fleet Integration).

Endpoints for managing NPU worker nodes and load balancing.
"""

import logging
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from models.database import Node, Setting
from models.schemas import (
    NPUCapabilities,
    NPUDetectionRequest,
    NPUDetectionResponse,
    NPULoadBalancingConfig,
    NPUNodeListResponse,
    NPUNodeStatusResponse,
    NPURoleAssignResponse,
)
from services.auth import get_current_user
from services.database import get_db
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/npu", tags=["npu"])

# Settings keys for NPU configuration
NPU_LB_STRATEGY_KEY = "npu_load_balancing_strategy"
NPU_MODEL_AFFINITY_KEY = "npu_model_affinity"


async def _get_npu_nodes(db: AsyncSession) -> list:
    """Get all nodes with npu-worker role."""
    result = await db.execute(select(Node))
    all_nodes = result.scalars().all()
    return [n for n in all_nodes if n.roles and "npu-worker" in n.roles]


async def _update_npu_data(db: AsyncSession, node: Node, updates: dict) -> None:
    """Merge updates into node.extra_data['npu'] and commit.

    Helper for trigger_npu_detection (Issue #813).
    """
    extra = node.extra_data or {}
    npu_data = extra.get("npu", {})
    npu_data.update(updates)
    extra["npu"] = npu_data
    node.extra_data = extra
    await db.commit()


async def _detect_npu_capabilities(
    ip_address: str, port: int
) -> tuple[Optional[NPUCapabilities], str]:
    """Query NPU worker health endpoint to detect capabilities.

    Helper for trigger_npu_detection (Issue #813).
    """
    url = f"http://{ip_address}:{port}/health"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None, f"NPU worker returned {resp.status_code}"

            data = resp.json()
            caps = NPUCapabilities(
                models=data.get("models", []),
                max_concurrent=data.get("maxConcurrent", 1),
                memory_gb=data.get("memoryGB", 0.0),
                device_type=data.get("deviceType", "unknown"),
                utilization=data.get("utilization", 0.0),
            )
            return caps, ""
    except httpx.ConnectError:
        return None, f"Cannot connect to NPU worker at {url}"
    except Exception as exc:
        return None, f"NPU detection failed: {exc}"


async def _get_node_npu_status(node: Node) -> NPUNodeStatusResponse:
    """Build NPU status response for a node."""
    # Get NPU-specific data from extra_data if available
    extra = node.extra_data or {}
    npu_data = extra.get("npu", {})

    capabilities = None
    if npu_data.get("capabilities"):
        capabilities = NPUCapabilities(**npu_data["capabilities"])

    return NPUNodeStatusResponse(
        node_id=node.node_id,
        capabilities=capabilities,
        loaded_models=npu_data.get("loaded_models", []),
        queue_depth=npu_data.get("queue_depth", 0),
        last_health_check=npu_data.get("last_health_check"),
        detection_status=npu_data.get("detection_status", "pending"),
        detection_error=npu_data.get("detection_error"),
    )


@router.get("/nodes", response_model=NPUNodeListResponse)
async def list_npu_nodes(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NPUNodeListResponse:
    """
    List all nodes with NPU worker role.

    Returns nodes that have the 'npu-worker' role assigned,
    along with their NPU capabilities and status.
    """
    npu_nodes = await _get_npu_nodes(db)

    nodes_status = []
    for node in npu_nodes:
        node_status = await _get_node_npu_status(node)
        nodes_status.append(node_status)

    return NPUNodeListResponse(
        nodes=nodes_status,
        total=len(nodes_status),
    )


@router.get("/nodes/{node_id}/status", response_model=NPUNodeStatusResponse)
async def get_npu_node_status(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NPUNodeStatusResponse:
    """
    Get NPU status for a specific node.

    Returns detailed NPU capabilities, loaded models, and health status.
    """
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    if not node.roles or "npu-worker" not in node.roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Node does not have npu-worker role",
        )

    return await _get_node_npu_status(node)


@router.post("/nodes/{node_id}/detect", response_model=NPUDetectionResponse)
async def trigger_npu_detection(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    request: Optional[NPUDetectionRequest] = None,
) -> NPUDetectionResponse:
    """
    Trigger NPU capability detection for a node.

    This queries the NPU worker service on the node to detect
    available hardware, models, and capabilities.
    """
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    if not node.roles or "npu-worker" not in node.roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Node does not have npu-worker role",
        )

    await _update_npu_data(
        db, node, {"detection_status": "pending", "detection_error": None}
    )

    # Query the NPU worker health endpoint (Issue #813)
    capabilities, error_msg = await _detect_npu_capabilities(
        node.ip_address, node.ssh_port or 8081
    )
    result_data = {"last_health_check": datetime.utcnow().isoformat()}
    if capabilities:
        result_data.update(
            detection_status="completed", capabilities=capabilities.model_dump()
        )
    else:
        result_data.update(detection_status="failed", detection_error=error_msg)

    await _update_npu_data(db, node, result_data)
    logger.info(
        "NPU detection for %s: %s", node_id, "success" if capabilities else error_msg
    )

    return NPUDetectionResponse(
        success=capabilities is not None,
        message="NPU detection completed." if capabilities else error_msg,
        node_id=node_id,
        capabilities=capabilities,
    )


@router.get("/load-balancing", response_model=NPULoadBalancingConfig)
async def get_load_balancing_config(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NPULoadBalancingConfig:
    """
    Get NPU load balancing configuration.

    Returns the current load balancing strategy and model affinity settings.
    """
    import json

    # Get strategy
    strategy_result = await db.execute(
        select(Setting).where(Setting.key == NPU_LB_STRATEGY_KEY)
    )
    strategy_setting = strategy_result.scalar_one_or_none()
    strategy = strategy_setting.value if strategy_setting else "round-robin"

    # Get model affinity
    affinity_result = await db.execute(
        select(Setting).where(Setting.key == NPU_MODEL_AFFINITY_KEY)
    )
    affinity_setting = affinity_result.scalar_one_or_none()
    model_affinity = {}
    if affinity_setting and affinity_setting.value:
        try:
            model_affinity = json.loads(affinity_setting.value)
        except json.JSONDecodeError:
            logger.warning("Invalid model affinity JSON, using empty dict")

    return NPULoadBalancingConfig(
        strategy=strategy,
        model_affinity=model_affinity,
    )


@router.post("/load-balancing", response_model=NPULoadBalancingConfig)
async def update_load_balancing_config(
    config: NPULoadBalancingConfig,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NPULoadBalancingConfig:
    """
    Update NPU load balancing configuration.

    Sets the load balancing strategy and model affinity mappings.
    """
    import json

    # Validate strategy
    valid_strategies = ["round-robin", "least-loaded", "model-affinity"]
    if config.strategy not in valid_strategies:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid strategy. Must be one of: {valid_strategies}",
        )

    # Update or create strategy setting
    strategy_result = await db.execute(
        select(Setting).where(Setting.key == NPU_LB_STRATEGY_KEY)
    )
    strategy_setting = strategy_result.scalar_one_or_none()

    if strategy_setting:
        strategy_setting.value = config.strategy
    else:
        strategy_setting = Setting(
            key=NPU_LB_STRATEGY_KEY,
            value=config.strategy,
            value_type="string",
            description="NPU load balancing strategy",
        )
        db.add(strategy_setting)

    # Update or create model affinity setting
    affinity_result = await db.execute(
        select(Setting).where(Setting.key == NPU_MODEL_AFFINITY_KEY)
    )
    affinity_setting = affinity_result.scalar_one_or_none()

    affinity_json = json.dumps(config.model_affinity)
    if affinity_setting:
        affinity_setting.value = affinity_json
    else:
        affinity_setting = Setting(
            key=NPU_MODEL_AFFINITY_KEY,
            value=affinity_json,
            value_type="json",
            description="NPU model affinity mappings",
        )
        db.add(affinity_setting)

    await db.commit()

    logger.info("NPU load balancing config updated: strategy=%s", config.strategy)

    return config


@router.post(
    "/nodes/{node_id}/assign-role",
    response_model=NPURoleAssignResponse,
)
async def assign_npu_role(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NPURoleAssignResponse:
    """
    Assign the npu-worker role to a node.

    This adds the npu-worker role and triggers capability detection.
    """
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    # Check if already has role
    current_roles = node.roles or []
    if "npu-worker" in current_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Node already has npu-worker role",
        )

    # Add the role
    node.roles = current_roles + ["npu-worker"]

    # Initialize NPU data in extra_data
    extra = node.extra_data or {}
    extra["npu"] = {
        "detection_status": "pending",
        "capabilities": None,
        "loaded_models": [],
        "queue_depth": 0,
    }
    node.extra_data = extra

    await db.commit()

    logger.info("NPU role assigned to node %s", node_id)

    return NPURoleAssignResponse(
        success=True,
        message="NPU worker role assigned. Detection will run automatically.",
        node_id=node_id,
        detection_triggered=True,
    )


@router.delete("/nodes/{node_id}/role")
async def remove_npu_role(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """
    Remove the npu-worker role from a node.

    This removes the role and clears NPU-specific data.
    """
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    # Check if has role
    current_roles = node.roles or []
    if "npu-worker" not in current_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Node does not have npu-worker role",
        )

    # Remove the role
    node.roles = [r for r in current_roles if r != "npu-worker"]

    # Clear NPU data from extra_data
    extra = node.extra_data or {}
    if "npu" in extra:
        del extra["npu"]
    node.extra_data = extra if extra else None

    await db.commit()

    logger.info("NPU role removed from node %s", node_id)

    return {
        "success": True,
        "message": "NPU worker role removed",
        "node_id": node_id,
    }
