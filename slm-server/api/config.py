# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Configuration API Routes (Issue #760)

Endpoints for managing per-node and global configuration.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from models.database import Node, NodeConfig
from models.schemas import (
    NodeConfigBulkResponse,
    NodeConfigResponse,
    NodeConfigSetRequest,
)
from services.auth import get_current_user
from services.database import get_db

logger = logging.getLogger(__name__)

# Router for global defaults
router = APIRouter(prefix="/config", tags=["configuration"])

# Router for node-specific config (added to nodes router separately)
node_config_router = APIRouter(tags=["node-configuration"])


def _cast_config_value(value: Optional[str], value_type: str):
    """Cast config value to appropriate type."""
    if value is None:
        return None

    if value_type == "int":
        return int(value)
    elif value_type == "bool":
        return value.lower() in ("true", "1", "yes")
    elif value_type == "json":
        return json.loads(value)
    return value


async def _get_config_with_fallback(
    db: AsyncSession, node_id: str, key: str
) -> Optional[NodeConfig]:
    """Get config for node, falling back to global default."""
    result = await db.execute(
        select(NodeConfig).where(
            NodeConfig.node_id == node_id,
            NodeConfig.config_key == key,
        )
    )
    config = result.scalar_one_or_none()
    if config:
        return config

    result = await db.execute(
        select(NodeConfig).where(
            NodeConfig.node_id.is_(None),
            NodeConfig.config_key == key,
        )
    )
    return result.scalar_one_or_none()


# =============================================================================
# Global Defaults Endpoints
# =============================================================================


@router.get("/defaults")
async def get_global_defaults(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    prefix: Optional[str] = Query(None, description="Filter by key prefix"),
) -> dict:
    """Get all global default configurations."""
    query = select(NodeConfig).where(NodeConfig.node_id.is_(None))

    if prefix:
        query = query.where(NodeConfig.config_key.startswith(prefix))

    query = query.order_by(NodeConfig.config_key)
    result = await db.execute(query)
    configs = result.scalars().all()

    return {
        "configs": [
            NodeConfigResponse(
                id=c.id,
                node_id=None,
                config_key=c.config_key,
                config_value=c.config_value,
                value_type=c.value_type,
                is_global=True,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in configs
        ],
        "total": len(configs),
    }


@router.get("/defaults/{key}")
async def get_global_default(
    key: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NodeConfigResponse:
    """Get a specific global default configuration."""
    result = await db.execute(
        select(NodeConfig).where(
            NodeConfig.node_id.is_(None),
            NodeConfig.config_key == key,
        )
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Global config '{key}' not found",
        )

    return NodeConfigResponse(
        id=config.id,
        node_id=None,
        config_key=config.config_key,
        config_value=config.config_value,
        value_type=config.value_type,
        is_global=True,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


@router.put("/defaults/{key}")
async def set_global_default(
    key: str,
    request: NodeConfigSetRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NodeConfigResponse:
    """Set a global default configuration."""
    result = await db.execute(
        select(NodeConfig).where(
            NodeConfig.node_id.is_(None),
            NodeConfig.config_key == key,
        )
    )
    config = result.scalar_one_or_none()

    if config:
        config.config_value = request.value
        config.value_type = request.value_type
        config.updated_at = datetime.utcnow()
    else:
        config = NodeConfig(
            node_id=None,
            config_key=key,
            config_value=request.value,
            value_type=request.value_type,
        )
        db.add(config)

    await db.commit()
    await db.refresh(config)

    logger.info("Global config '%s' set to '%s'", key, request.value)

    return NodeConfigResponse(
        id=config.id,
        node_id=None,
        config_key=config.config_key,
        config_value=config.config_value,
        value_type=config.value_type,
        is_global=True,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


@router.delete("/defaults/{key}")
async def delete_global_default(
    key: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """Delete a global default configuration."""
    result = await db.execute(
        select(NodeConfig).where(
            NodeConfig.node_id.is_(None),
            NodeConfig.config_key == key,
        )
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Global config '{key}' not found",
        )

    await db.delete(config)
    await db.commit()

    logger.info("Global config '%s' deleted", key)

    return {"message": f"Global config '{key}' deleted", "key": key}


# =============================================================================
# Node-Specific Config Endpoints
# =============================================================================


@node_config_router.get("/{node_id}/config")
async def get_node_config(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    prefix: Optional[str] = Query(None, description="Filter by key prefix"),
    include_globals: bool = Query(True, description="Include global defaults"),
) -> NodeConfigBulkResponse:
    """
    Get all configuration for a node.

    Returns node-specific configs merged with global defaults.
    """
    node_result = await db.execute(select(Node).where(Node.node_id == node_id))
    if not node_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    configs: dict = {}

    if include_globals:
        query = select(NodeConfig).where(NodeConfig.node_id.is_(None))
        if prefix:
            query = query.where(NodeConfig.config_key.startswith(prefix))
        result = await db.execute(query)
        for config in result.scalars().all():
            configs[config.config_key] = config.config_value

    query = select(NodeConfig).where(NodeConfig.node_id == node_id)
    if prefix:
        query = query.where(NodeConfig.config_key.startswith(prefix))
    result = await db.execute(query)
    for config in result.scalars().all():
        configs[config.config_key] = config.config_value

    return NodeConfigBulkResponse(node_id=node_id, configs=configs)


@node_config_router.get("/{node_id}/config/{key}")
async def get_node_config_key(
    node_id: str,
    key: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NodeConfigResponse:
    """Get a specific config for a node (with fallback to global)."""
    node_result = await db.execute(select(Node).where(Node.node_id == node_id))
    if not node_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    config = await _get_config_with_fallback(db, node_id, key)

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Config '{key}' not found for node or globally",
        )

    return NodeConfigResponse(
        id=config.id,
        node_id=config.node_id,
        config_key=config.config_key,
        config_value=config.config_value,
        value_type=config.value_type,
        is_global=config.node_id is None,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


@node_config_router.put("/{node_id}/config/{key}")
async def set_node_config_key(
    node_id: str,
    key: str,
    request: NodeConfigSetRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NodeConfigResponse:
    """Set a config for a specific node."""
    node_result = await db.execute(select(Node).where(Node.node_id == node_id))
    if not node_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    result = await db.execute(
        select(NodeConfig).where(
            NodeConfig.node_id == node_id,
            NodeConfig.config_key == key,
        )
    )
    config = result.scalar_one_or_none()

    if config:
        config.config_value = request.value
        config.value_type = request.value_type
        config.updated_at = datetime.utcnow()
    else:
        config = NodeConfig(
            node_id=node_id,
            config_key=key,
            config_value=request.value,
            value_type=request.value_type,
        )
        db.add(config)

    await db.commit()
    await db.refresh(config)

    logger.info("Node %s config '%s' set to '%s'", node_id, key, request.value)

    return NodeConfigResponse(
        id=config.id,
        node_id=config.node_id,
        config_key=config.config_key,
        config_value=config.config_value,
        value_type=config.value_type,
        is_global=False,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


@node_config_router.delete("/{node_id}/config/{key}")
async def delete_node_config_key(
    node_id: str,
    key: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """Delete node-specific config (falls back to global if exists)."""
    result = await db.execute(
        select(NodeConfig).where(
            NodeConfig.node_id == node_id,
            NodeConfig.config_key == key,
        )
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node-specific config '{key}' not found",
        )

    await db.delete(config)
    await db.commit()

    logger.info("Node %s config '%s' deleted", node_id, key)

    return {
        "message": f"Node config '{key}' deleted (will use global default if exists)",
        "node_id": node_id,
        "key": key,
    }
