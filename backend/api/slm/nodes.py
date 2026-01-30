# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Nodes API

DEPRECATED: This file should be deleted as part of layer separation (Issue #729).
All SLM functionality has been moved to slm-server.
See: slm-server/api/nodes.py for the active implementation.

REST endpoints for node management.
"""

# TODO: DELETE THIS FILE - Part of Issue #729 layer separation
# This file is non-functional after removal of backend/services/slm/
# SLM server at 172.16.168.19 provides these endpoints

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from backend.models.infrastructure import NodeState
# REMOVED: from backend.services.slm.db_service import SLMDatabaseService
# REMOVED: from backend.services.slm.state_machine import InvalidStateTransition

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/slm/nodes", tags=["SLM Nodes"])

# Singleton database service
_db_service: Optional[SLMDatabaseService] = None


def get_db_service() -> SLMDatabaseService:
    """Get or create database service singleton."""
    global _db_service
    if _db_service is None:
        _db_service = SLMDatabaseService()
    return _db_service


# ==================== Pydantic Models ====================

class NodeCreate(BaseModel):
    """Request model for creating a node."""
    name: str = Field(..., min_length=1, max_length=255)
    ip_address: str = Field(..., pattern=r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
    ssh_port: int = Field(default=22, ge=1, le=65535)
    ssh_user: str = Field(default="autobot", max_length=50)
    capability_tags: List[str] = Field(default_factory=list)
    current_role: Optional[str] = None


class NodeResponse(BaseModel):
    """Response model for node data."""
    id: str
    name: str
    ip_address: str
    ssh_port: int
    ssh_user: str
    state: str
    current_role: Optional[str]
    capability_tags: List[str]
    consecutive_failures: int
    last_heartbeat: Optional[str]

    class Config:
        from_attributes = True


class NodeListResponse(BaseModel):
    """Response model for node list."""
    nodes: List[NodeResponse]
    total: int


class StateUpdateRequest(BaseModel):
    """Request model for state update."""
    state: str
    trigger: str = "api"
    details: Optional[dict] = None


# ==================== Endpoints ====================

@router.get("", response_model=NodeListResponse)
async def list_nodes(state: Optional[str] = None):
    """List all nodes, optionally filtered by state."""
    db = get_db_service()
    state_filter = NodeState(state) if state else None
    nodes = db.get_all_nodes(state=state_filter)

    return NodeListResponse(
        nodes=[_node_to_response(n) for n in nodes],
        total=len(nodes),
    )


@router.post("", response_model=NodeResponse, status_code=status.HTTP_201_CREATED)
async def create_node(node: NodeCreate):
    """Create a new node."""
    db = get_db_service()

    # Check for duplicates
    if db.get_node_by_name(node.name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Node with name '{node.name}' already exists",
        )
    if db.get_node_by_ip(node.ip_address):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Node with IP '{node.ip_address}' already exists",
        )

    created = db.create_node(
        name=node.name,
        ip_address=node.ip_address,
        ssh_port=node.ssh_port,
        ssh_user=node.ssh_user,
        capability_tags=node.capability_tags,
        current_role=node.current_role,
    )

    return _node_to_response(created)


@router.get("/{node_id}", response_model=NodeResponse)
async def get_node(node_id: str):
    """Get node by ID."""
    db = get_db_service()
    node = db.get_node(node_id)

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node '{node_id}' not found",
        )

    return _node_to_response(node)


@router.post("/{node_id}/state", response_model=NodeResponse)
async def update_node_state(node_id: str, request: StateUpdateRequest):
    """Update node state with transition validation."""
    db = get_db_service()

    try:
        new_state = NodeState(request.state)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid state: {request.state}",
        )

    try:
        node = db.update_node_state(
            node_id=node_id,
            new_state=new_state,
            trigger=request.trigger,
            details=request.details,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InvalidStateTransition as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return _node_to_response(node)


@router.delete("/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node(node_id: str):
    """Delete a node (must be in UNKNOWN or ERROR state)."""
    db = get_db_service()
    node = db.get_node(node_id)

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node '{node_id}' not found",
        )

    # Only allow deletion of nodes in safe states
    safe_states = {NodeState.UNKNOWN.value, NodeState.ERROR.value}
    if node.state not in safe_states:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete node in state '{node.state}'. Must be UNKNOWN or ERROR.",
        )

    db.delete_node(node_id)


def _node_to_response(node) -> NodeResponse:
    """Convert SLMNode to NodeResponse."""
    return NodeResponse(
        id=node.id,
        name=node.name,
        ip_address=node.ip_address,
        ssh_port=node.ssh_port,
        ssh_user=node.ssh_user,
        state=node.state,
        current_role=node.current_role,
        capability_tags=node.capability_tags or [],
        consecutive_failures=node.consecutive_failures,
        last_heartbeat=node.last_heartbeat.isoformat() if node.last_heartbeat else None,
    )
