# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Admin view of deleted conversation files waiting on a human, and the reset for a stuck one (#20234, #17038).

A deleted file's bytes stay on disk until an approved proposal removes them. A file whose removal was
refused ``AUTOBOT_CONVERSATION_FILE_CLEANUP_MAX_ATTEMPTS`` times is no longer proposed (a "stuck" file);
without this module nothing showed it to anyone. Mounted at ``/api/conversation-files/cleanup`` and
shown by ``components/llc/StuckFileCleanupPanel.vue``.

* ``GET /cleanup/status`` -- pending and stuck counts, bytes, and the stuck list. Read only.
* ``POST /cleanup/{file_id}/reset`` -- a person lets a stuck file be proposed again. It zeroes the
  refusal counter and audits who did it. It removes no bytes: the new proposal still needs an approval.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from auth_middleware import check_admin_permission, resolve_human_user
from autobot_shared.logging_manager import get_logger
from conversation_file_cleanup import cleanup_status, reset_cleanup_attempts
from services.audit_logger import audit_log

logger = get_logger(__name__)

router = APIRouter(prefix="/cleanup", dependencies=[Depends(check_admin_permission)])


def _manager(request: Request):
    manager = getattr(request.app.state, "conversation_file_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="File management service temporarily unavailable")
    return manager


@router.get("/status")
async def get_cleanup_status(request: Request) -> Dict[str, Any]:
    """Deleted files whose bytes still await removal, and those stuck after repeated refusals."""
    return await cleanup_status(_manager(request))


@router.post("/{file_id}/reset")
async def reset_stuck_cleanup(request: Request, file_id: str) -> Dict[str, Any]:
    """Let a stuck file be proposed again; a person's action, audited, and it removes nothing."""
    manager = _manager(request)
    if not await reset_cleanup_attempts(manager, file_id):
        raise HTTPException(status_code=404, detail="No refused cleanup is recorded for this file")
    user = await resolve_human_user(request) or {}
    await audit_log(
        "conversation_file.cleanup_reset",
        user_id=user.get("username") or user.get("user_id") or "internal-service",
        resource=f"conversation_file:{file_id}",
        details={"effect": "file may be proposed for removal again; no bytes removed"},
    )
    from services.conversation_file_cleanup_proposals import propose_due_cleanups_logged

    await propose_due_cleanups_logged(manager)  # raises a proposal only; the bytes wait for an approval
    return {"file_id": file_id, "reset": True}
