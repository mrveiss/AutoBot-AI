# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Host selection endpoints for the agent terminal (#744).

Extracted from ``api/agent_terminal.py`` (#14959) the way ``terminal_tools``
was extracted from ``api/terminal.py`` (#185): a sub-router included by the
parent, so every path stays exactly where it was under ``/agent-terminal``.

These endpoints let an agent ask a human which infrastructure host an SSH action
should target, and they own state nothing else in the parent module touches --
the pending-selection store and its lock. That made them the one self-contained
group in a file that had reached its recorded size ceiling.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException

from api.schemas_system import TerminalHostSelectionRequest
from api.schemas_terminal import (
    AgentTerminalHostSelectionCancelResponse,
    AgentTerminalHostSelectionGetResponse,
    AgentTerminalHostSelectionRequestResponse,
    AgentTerminalHostSelectionSubmitResponse,
    AgentTerminalPendingSelectionsResponse,
)
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["agent-terminal"])

# In-memory store for pending host selection requests
# In production, this would use Redis for persistence
_pending_host_selections: Dict[str, Dict] = {}
# Issue #10783 C: guard all check-then-act and iterate-while-mutate sequences
_pending_host_selections_lock = asyncio.Lock()


@router.post("/host-selection/request", response_model=AgentTerminalHostSelectionRequestResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="request_host_selection",
    error_code_prefix="AGENT_TERMINAL",
)
async def request_host_selection(
    current_user: dict = Depends(get_current_user),
    request: TerminalHostSelectionRequest = None,
):
    """
    Agent requests host selection for SSH action.

    Issue #744: Requires authenticated user.

    This endpoint creates a pending host selection request that the frontend
    will display to the user. The user selects from available infrastructure
    hosts, and the selection is returned via the /host-selection/{request_id}
    endpoint.

    Flow:
    1. Agent calls POST /host-selection/request with command/purpose
    2. Backend returns request_id with status="pending_selection"
    3. Frontend shows HostSelectionDialog to user
    4. User selects host and calls POST /host-selection/{request_id}/select
    5. Agent polls GET /host-selection/{request_id} to get selection result
    """
    request_id = str(uuid.uuid4())

    # Create pending selection request
    async with _pending_host_selections_lock:
        _pending_host_selections[request_id] = {
            "request_id": request_id,
            "agent_session_id": request.agent_session_id,
            "command": request.command,
            "purpose": request.purpose,
            "preferred_host_id": request.preferred_host_id,
            "allow_auto_select": request.allow_auto_select,
            "status": "pending_selection",
            "selected_host_id": None,
            "selected_host_name": None,
            "connection_info": None,
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
            "updated_at": None,
        }

    logger.info(f"Host selection requested: {request_id}")

    return {
        "request_id": request_id,
        "status": "pending_selection",
        "message": "Host selection dialog should be shown to user",
    }


@router.get("/host-selection/{request_id}", response_model=AgentTerminalHostSelectionGetResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_host_selection",
    error_code_prefix="AGENT_TERMINAL",
)
async def get_host_selection(
    request_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Get the status/result of a host selection request.

    Issue #744: Requires authenticated user.

    Agent polls this endpoint to check if user has made a selection.

    Returns:
    - status: "pending_selection", "selected", or "cancelled"
    - If selected: includes host details and connection info
    """
    async with _pending_host_selections_lock:
        if request_id not in _pending_host_selections:
            raise HTTPException(status_code=404, detail=f"Host selection request {request_id} not found")
        selection = dict(_pending_host_selections[request_id])

    return {
        "request_id": selection["request_id"],
        "status": selection["status"],
        "selected_host_id": selection["selected_host_id"],
        "selected_host_name": selection["selected_host_name"],
        "connection_info": selection["connection_info"],
        "created_at": selection["created_at"],
        "updated_at": selection["updated_at"],
    }


@router.post("/host-selection/{request_id}/select", response_model=AgentTerminalHostSelectionSubmitResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="submit_host_selection",
    error_code_prefix="AGENT_TERMINAL",
)
async def submit_host_selection(
    request_id: str,
    current_user: dict = Depends(get_current_user),
    host_id: str = None,
    host_name: str = None,
    host: str = None,
    ssh_port: int = 22,
    username: str = "root",
    remember_choice: bool = False,
):
    """
    User submits their host selection.

    Issue #744: Requires authenticated user.

    Called by frontend when user selects a host from the dialog.

    Args:
        request_id: The pending selection request ID
        host_id: Selected host ID from secrets
        host_name: Display name of the host
        host: Hostname or IP address
        ssh_port: SSH port number
        username: SSH username
        remember_choice: Whether to use this host for future SSH commands
    """
    async with _pending_host_selections_lock:
        if request_id not in _pending_host_selections:
            raise HTTPException(status_code=404, detail=f"Host selection request {request_id} not found")

        selection = _pending_host_selections[request_id]

        if selection["status"] != "pending_selection":
            raise HTTPException(
                status_code=400,
                detail=f"Host selection request {request_id} is not pending (status: {selection['status']})",
            )

        # Update selection with user's choice
        selection["status"] = "selected"
        selection["selected_host_id"] = host_id
        selection["selected_host_name"] = host_name
        selection["connection_info"] = {
            "host": host,
            "ssh_port": ssh_port,
            "username": username,
        }
        selection["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
        selection["remember_choice"] = remember_choice
        connection_info = dict(selection["connection_info"])

    logger.info(f"Host selected for request {request_id}: {host_name} ({username}@{host}:{ssh_port})")

    return {
        "status": "selected",
        "request_id": request_id,
        "selected_host_id": host_id,
        "selected_host_name": host_name,
        "connection_info": connection_info,
    }


@router.post("/host-selection/{request_id}/cancel", response_model=AgentTerminalHostSelectionCancelResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cancel_host_selection",
    error_code_prefix="AGENT_TERMINAL",
)
async def cancel_host_selection(
    request_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    User cancels host selection.

    Issue #744: Requires authenticated user.

    Called by frontend when user closes the dialog without selecting.
    """
    async with _pending_host_selections_lock:
        if request_id not in _pending_host_selections:
            raise HTTPException(status_code=404, detail=f"Host selection request {request_id} not found")

        selection = _pending_host_selections[request_id]

        if selection["status"] != "pending_selection":
            raise HTTPException(
                status_code=400,
                detail=f"Host selection request {request_id} is not pending (status: {selection['status']})",
            )

        # Mark as cancelled
        selection["status"] = "cancelled"
        selection["updated_at"] = datetime.now(tz=timezone.utc).isoformat()

    logger.info(f"Host selection cancelled for request {request_id}")

    return {
        "status": "cancelled",
        "request_id": request_id,
    }


@router.get("/host-selection", response_model=AgentTerminalPendingSelectionsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_pending_host_selections",
    error_code_prefix="AGENT_TERMINAL",
)
async def list_pending_host_selections(
    current_user: dict = Depends(get_current_user),
):
    """
    List all pending host selection requests.

    Issue #744: Requires authenticated user.

    Frontend uses this to show any pending selection dialogs on page load.
    """
    async with _pending_host_selections_lock:
        pending = [
            {
                "request_id": s["request_id"],
                "command": s["command"],
                "purpose": s["purpose"],
                "created_at": s["created_at"],
            }
            for s in _pending_host_selections.values()
            if s["status"] == "pending_selection"
        ]

    return {
        "status": "success",
        "pending_count": len(pending),
        "pending_selections": pending,
    }
