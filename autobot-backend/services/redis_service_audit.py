# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Audit and refusal bookkeeping of :mod:`services.redis_service_manager` (#22030).

Split out of the manager to keep it within the file-size ceiling.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from autobot_shared.logging_manager import get_logger
from services.redis_service_errors import clear_resolved_node
from type_defs.common import Metadata

logger = get_logger(__name__)


def audit_event(enabled: bool, event_type: str, data: Metadata, user_id: str | None = None) -> None:
    """Log one audit event (no-op when audit logging is off)."""
    if not enabled:
        return
    try:
        entry = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "event_type": event_type,
            "user_id": user_id,
            "data": data,
        }
        logger.info("AUDIT: %s", json.dumps(entry))
    except Exception as e:
        logger.error("Audit logging failed: %s", e)


async def record_refusal(manager, operation: str, error: Exception, user_id: str | None = None) -> None:
    """Count, audit and un-cache after an unresolved node or refused credential; the caller then re-raises."""
    logger.error("Redis %s cannot reach the SLM service API: %s", operation, error)
    clear_resolved_node()  # the role may have moved; the next call must ask again, not wait out the cache TTL
    await manager._record_error()
    manager._audit_log(f"redis_service_{operation}_refused", {"error": type(error).__name__}, user_id=user_id)
