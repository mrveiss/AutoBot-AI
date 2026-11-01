# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A durable paper trail for restoring or deleting a knowledge backup (#19721, #17038).

The entry is committed before the file or the facts change, and no entry means the action does not run.
"""

from __future__ import annotations

from services.audit.taxonomy import AuditAction
from services.audit_logger import audit_log


async def audit_backup_action(action: AuditAction, actor: str, filename: str) -> bool:
    """Whether the audit entry for *action* on the backup *filename* was committed."""
    return await audit_log(action.value, user_id=actor, resource=filename, durable=True)
