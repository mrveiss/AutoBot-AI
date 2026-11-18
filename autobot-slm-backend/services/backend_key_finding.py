# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The backend refusing the SLM's internal API key becomes a finding the admin sees (#20750).

Every SLM call to the backend's System vault answered 401 for a week, and nothing outside the
backend's access log showed it. The SLM and the backend each hold an ``AUTOBOT_INTERNAL_API_KEY``.
Install renders the backend's from the SLM's, but an update that finds them different keeps the
backend's, because changing a stored credential needs the owner's approval (#17038). So a mismatch
can persist, and this makes it visible: one unresolved error event on the SLM's node, which the
Monitoring view's error list shows, until someone resolves it.

Re-aligning the key is not done here. That is an approval-queue action (#20750, PR 2).
"""

import time
import uuid

from sqlalchemy import select, text

from autobot_shared.env_utils import env_float
from autobot_shared.logging_manager import get_logger
from config import settings
from models.database import EventSeverity, NodeEvent
from services.database import db_service

logger = get_logger(__name__)

#: The event type of the finding; one unresolved event of this type stands for the whole mismatch.
FINDING_EVENT_TYPE = "internal_key_refused"
#: Serialises check-then-insert across SLM workers, so concurrent 401s write one finding (the
#: fleet_sync_guard pattern; the id matches the issue, as there).
_FINDING_ADVISORY_LOCK_ID = 20750
#: A burst of refused calls checks the database once per this many seconds, not once per call.
FINDING_CHECK_INTERVAL_S = env_float("AUTOBOT_SLM_KEY_FINDING_CHECK_INTERVAL_S", 60.0)
_last_check = [float("-inf")]

FINDING_MESSAGE = (
    "The backend refused the SLM's internal API key, so the SLM's AUTOBOT_INTERNAL_API_KEY differs "
    "from the backend's. Until they match, every SLM call into the backend fails: the System vault "
    "(SSO and LLM secrets, the VNC password registration) and the voice, personality and memory "
    "proxies. Re-aligning the backend's key to the SLM's is a credential change and needs approval (#20750)."
)


async def report_backend_refused_internal_key(path: str) -> None:
    """Record the finding once, until resolved. Never raises: the caller's own error stands."""
    now = time.monotonic()
    if now - _last_check[0] < FINDING_CHECK_INTERVAL_S:
        return
    _last_check[0] = now
    try:
        async with db_service.session() as db:
            # Held to the commit: a second worker's check waits for this insert, then sees it.
            await db.execute(
                text("SELECT pg_advisory_xact_lock(:lock_id)").bindparams(lock_id=_FINDING_ADVISORY_LOCK_ID)
            )
            pending = await db.execute(
                select(NodeEvent.id)
                .where(NodeEvent.node_id == settings.slm_node_id)
                .where(NodeEvent.event_type == FINDING_EVENT_TYPE)
                .where(NodeEvent.resolved.is_(False))
                .limit(1)
            )
            if pending.scalar() is not None:
                return
            db.add(
                NodeEvent(
                    event_id=f"keyref-{uuid.uuid4().hex[:16]}",
                    node_id=settings.slm_node_id,
                    event_type=FINDING_EVENT_TYPE,
                    severity=EventSeverity.ERROR.value,
                    message=FINDING_MESSAGE,
                    details={"path": path, "issue": 20750},
                )
            )
            await db.commit()
    except Exception as exc:  # the finding is best-effort; the 401 itself is still raised to the caller
        logger.warning("Could not record the internal-key finding: %s", exc)
