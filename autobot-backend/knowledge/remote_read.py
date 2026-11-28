# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Gate for reads of the remote AI-stack service, whose backing store this repo cannot see (#16665, #19646).

``services/ai_stack_client.py`` posts no caller identity to the service and its answers are opaque, so no
per-fact filter can apply to them. Whether it reads user-private facts is not established from this
repository (``autobot-ai-stack`` holds only a README), so the read fails closed: only an admin, who may
read any fact on an explicit read API, reaches it, and each such read is audited like a local admin read.
"""

from fastapi import HTTPException

from autobot_shared.logging_manager import get_logger
from knowledge.search_filters import audit_admin_read, caller_reader

logger = get_logger(__name__)


def remote_read_is_admin(current_user) -> bool:
    """Whether *current_user* may read the remote service; 401 when the caller cannot be resolved."""
    return caller_reader(current_user).is_admin


async def admit_remote_read(current_user, surface: str) -> None:
    """Admit an admin to the remote AI-stack read on *surface*, audited; refuse everyone else.

    Raises 401 (unresolvable caller), 403 (not an admin) or 503 (the audit entry could not be written).
    Call it before the remote request, outside any ``try`` that swallows errors.
    """
    reader = caller_reader(current_user)
    if not reader.is_admin:
        raise HTTPException(status_code=403, detail="Admin permission required for this operation")
    details = {"source": "ai_stack_remote", "surface": surface, "fact_ids": [], "count": 0}
    if not await audit_admin_read(reader.user_id, details, durable=False):  # names no facts (#19860)
        raise HTTPException(status_code=503, detail="Audit unavailable; the read is withheld")
