# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Activity Tracking Utility

Issue #873 - Activity Tracking Integration Hooks (#608 Phase 5)

Centralized utility for tracking user activities. Originally covered
terminal/file/browser/desktop; #16466 retired the terminal/file/browser
paths (and secret-usage detection, which only they used) as dead code --
#873's own acceptance checklist for those three was never completed, and
neither had a caller anywhere in the backend. Only desktop tracking was
ever actually wired (integrations/desktop_tracking.py -> api/vnc_proxy.py),
so that's what remains here.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc
from models.activities import DesktopActivityModel

logger = get_logger(__name__)


async def track_desktop_activity(
    db: AsyncSession,
    user_id: uuid.UUID,
    action: str,
    session_id: str | None = None,
    coordinates: tuple[int, int] | None = None,
    window_title: str | None = None,
    input_text: str | None = None,
    screenshot_path: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> uuid.UUID:
    """
    Track desktop automation activity.

    Args:
        db: Database session
        user_id: User who performed the action
        action: Action type (click, type, move, screenshot, window_focus)
        session_id: Optional chat session ID
        coordinates: Screen coordinates (x, y)
        window_title: Target window title
        input_text: Text typed
        screenshot_path: Path to screenshot
        metadata: Additional metadata

    Returns:
        Activity ID
    """
    activity = DesktopActivityModel(
        id=uuid.uuid4(),
        user_id=user_id,
        session_id=session_id,
        action=action,
        coordinates=coordinates,
        window_title=window_title,
        input_text=input_text,
        screenshot_path=screenshot_path,
        metadata=metadata or {},
        timestamp=now_utc(),
    )

    db.add(activity)
    await db.commit()
    await db.refresh(activity)

    logger.info(f"Tracked desktop activity: user={user_id}, " f"action={action}")

    return activity.id
