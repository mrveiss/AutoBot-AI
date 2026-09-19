# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The workflow automation WebSocket, authenticated and owner-scoped (#17009).

Moved out of ``routes.py``. That endpoint accepted before any check, not even the
Origin header. It let any caller write its socket over another session's slot, and
it ran ``automation_control`` (pause, resume, cancel, approve_step, skip_step) on
**any** workflow in the process.

- The caller is authenticated before the socket is accepted (``open_authenticated_ws``).
- The session slot is claimed for that user. Another user's live slot is refused,
  and a disconnect frees only the caller's own socket.
- ``automation_control`` runs only for an admin or the workflow's recorded owner.
  No workflow creator records ``owner_id`` today, so in practice this is admin-only
  until the owner model lands (#17014).
"""

import json

from fastapi import WebSocket, WebSocketDisconnect

from api.ws_security import open_authenticated_ws
from autobot_shared.auth.permissions import is_admin_role
from autobot_shared.logging_manager import get_logger

from .models import WorkflowControlRequest

logger = get_logger(__name__)


def may_control(manager, workflow_id: str, user: dict) -> bool:
    """Whether *user* may steer *workflow_id*: an admin, or the owner the workflow records."""
    if is_admin_role(user.get("role")):
        return True
    workflow = manager.active_workflows.get(workflow_id)
    owner = getattr(workflow, "owner_id", None)
    return bool(owner) and owner in (user.get("user_id"), user.get("username"))


async def serve_workflow_socket(websocket: WebSocket, session_id: str, manager) -> None:
    """Authenticate, claim the session slot, then relay the caller's control messages."""
    messenger = manager.messenger
    user = await open_authenticated_ws(websocket)
    if user is None:
        return
    if not messenger.claim_session(session_id, websocket, user.get("username")):
        await websocket.close(code=1008, reason="Session belongs to another user")
        return
    try:
        while True:
            message = json.loads(await websocket.receive_text())
            if message.get("type") == "automation_control":
                await _control(websocket, manager, message, user)
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for session %s", session_id)
    except Exception as e:
        logger.error("WebSocket error for session %s: %s", session_id, e)
    finally:
        messenger.release_session(session_id, websocket)


async def _control(websocket: WebSocket, manager, message: dict, user: dict) -> None:
    """Apply one ``automation_control`` message, if the caller may steer that workflow."""
    workflow_id, action = message.get("workflow_id"), message.get("action")
    if not (workflow_id and action):
        return
    if not may_control(manager, workflow_id, user):
        logger.warning("Refused %s: %s on workflow %s", user.get("username"), action, workflow_id)
        await websocket.send_json({"type": "automation_control_refused", "workflow_id": workflow_id})
        return
    await manager.handle_workflow_control(WorkflowControlRequest(workflow_id=workflow_id, action=action))
