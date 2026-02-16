# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Desktop Automation Activity Tracking Integration

Issue #873 - Activity Tracking Integration Hooks (#608 Phase 5)

Integration hooks for tracking desktop automation activities (noVNC).
"""

import logging
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from backend.utils.activity_tracker import track_desktop_activity

logger = logging.getLogger(__name__)


async def track_desktop_action(
    db: AsyncSession,
    user_id: uuid.UUID,
    action: str,
    session_id: Optional[str] = None,
    coordinates: Optional[tuple[int, int]] = None,
    window_title: Optional[str] = None,
    input_text: Optional[str] = None,
    screenshot_path: Optional[str] = None,
    app_name: Optional[str] = None,
) -> uuid.UUID:
    """
    Track desktop automation action.

    Integration point for noVNC and GUI automation to record activities.

    Args:
        db: Database session
        user_id: User who performed the action
        action: Action type (click, type, move, screenshot, window_focus)
        session_id: Optional chat session ID
        coordinates: Screen coordinates (x, y)
        window_title: Target window title
        input_text: Text typed
        screenshot_path: Path to screenshot
        app_name: Application name

    Returns:
        Activity ID

    Example:
        >>> async with get_db_session() as db:
        ...     activity_id = await track_desktop_action(
        ...         db=db,
        ...         user_id=uuid.UUID(...),
        ...         action="click",
        ...         coordinates=(500, 300),
        ...         window_title="Visual Studio Code",
        ...     )
    """
    metadata = {}
    if app_name:
        metadata["app"] = app_name

    try:
        activity_id = await track_desktop_activity(
            db=db,
            user_id=user_id,
            action=action,
            session_id=session_id,
            coordinates=coordinates,
            window_title=window_title,
            input_text=input_text,
            screenshot_path=screenshot_path,
            metadata=metadata,
        )

        logger.info(f"Desktop activity tracked: user={user_id}, " f"action={action}")

        return activity_id

    except Exception as e:
        logger.error(
            f"Failed to track desktop activity: {e}",
            exc_info=True,
        )
        raise


async def track_mouse_click(
    db: AsyncSession,
    user_id: uuid.UUID,
    x: int,
    y: int,
    session_id: Optional[str] = None,
    window_title: Optional[str] = None,
) -> uuid.UUID:
    """
    Track mouse click.

    Args:
        db: Database session
        user_id: User who clicked
        x: X coordinate
        y: Y coordinate
        session_id: Optional chat session ID
        window_title: Window title if available

    Returns:
        Activity ID
    """
    return await track_desktop_action(
        db=db,
        user_id=user_id,
        action="click",
        session_id=session_id,
        coordinates=(x, y),
        window_title=window_title,
    )


async def track_keyboard_input(
    db: AsyncSession,
    user_id: uuid.UUID,
    text: str,
    session_id: Optional[str] = None,
    window_title: Optional[str] = None,
) -> uuid.UUID:
    """
    Track keyboard input.

    Args:
        db: Database session
        user_id: User who typed
        text: Text typed
        session_id: Optional chat session ID
        window_title: Window title if available

    Returns:
        Activity ID
    """
    return await track_desktop_action(
        db=db,
        user_id=user_id,
        action="type",
        session_id=session_id,
        input_text=text,
        window_title=window_title,
    )


async def track_screenshot_capture(
    db: AsyncSession,
    user_id: uuid.UUID,
    screenshot_path: str,
    session_id: Optional[str] = None,
    window_title: Optional[str] = None,
) -> uuid.UUID:
    """
    Track screenshot capture.

    Args:
        db: Database session
        user_id: User who captured screenshot
        screenshot_path: Path to saved screenshot
        session_id: Optional chat session ID
        window_title: Window title if available

    Returns:
        Activity ID
    """
    return await track_desktop_action(
        db=db,
        user_id=user_id,
        action="screenshot",
        session_id=session_id,
        screenshot_path=screenshot_path,
        window_title=window_title,
    )


async def track_window_focus(
    db: AsyncSession,
    user_id: uuid.UUID,
    window_title: str,
    session_id: Optional[str] = None,
    app_name: Optional[str] = None,
) -> uuid.UUID:
    """
    Track window focus change.

    Args:
        db: Database session
        user_id: User who focused window
        window_title: Window title
        session_id: Optional chat session ID
        app_name: Application name

    Returns:
        Activity ID
    """
    return await track_desktop_action(
        db=db,
        user_id=user_id,
        action="window_focus",
        session_id=session_id,
        window_title=window_title,
        app_name=app_name,
    )
