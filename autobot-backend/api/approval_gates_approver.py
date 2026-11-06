# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-action approver role for the approval gates' approve route (#20046, owner ruling 2026-11-06)."""

from fastapi import HTTPException, status

from autobot_shared.auth.permissions import is_admin_role
from services.approval_execution import is_admin_only_action
from services.audit_logger import audit_log


async def require_action_approver_role(approval, current_user: dict) -> None:
    """403 and audit a non-admin approving an admin-only action (#20046), in addition to the human check."""
    action = (approval.context or {}).get("action")
    if not is_admin_only_action(action) or is_admin_role(current_user.get("role")):
        return
    await audit_log(
        "approval.approve",
        result="denied",
        durable=True,
        user_id=current_user.get("username"),
        resource=f"approval:{approval.id}",
        details={"reason": "admin role required for this action", "action": action},
    )
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="approving this action requires the admin role")
