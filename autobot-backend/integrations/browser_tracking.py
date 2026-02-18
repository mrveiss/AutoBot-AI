# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Browser Automation Activity Tracking Integration

Issue #873 - Activity Tracking Integration Hooks (#608 Phase 5)

Integration hooks for tracking browser automation activities.
"""

import logging
import uuid
from typing import Any, Optional

from backend.utils.activity_tracker import track_browser_activity
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def track_browser_action(
    db: AsyncSession,
    user_id: uuid.UUID,
    url: str,
    action: str,
    session_id: Optional[str] = None,
    selector: Optional[str] = None,
    input_value: Optional[str] = None,
    secrets_used: Optional[list[uuid.UUID]] = None,
    status_code: Optional[int] = None,
    redirect_url: Optional[str] = None,
) -> uuid.UUID:
    """
    Track browser automation action.

    Integration point for browser worker to record automation activities.

    Args:
        db: Database session
        user_id: User who performed the action
        url: Target URL
        action: Action type (navigate, click, type, submit, scroll)
        session_id: Optional chat session ID
        selector: CSS selector for targeted element
        input_value: Value entered (for type/submit actions)
        secrets_used: List of secret IDs used
        status_code: HTTP status code
        redirect_url: Redirect URL if applicable

    Returns:
        Activity ID

    Example:
        >>> async with get_db_session() as db:
        ...     activity_id = await track_browser_action(
        ...         db=db,
        ...         user_id=uuid.UUID(...),
        ...         url="https://example.com",
        ...         action="navigate",
        ...         status_code=200,
        ...     )
    """
    metadata: dict[str, Any] = {}
    if status_code:
        metadata["status_code"] = status_code
    if redirect_url:
        metadata["redirect_url"] = redirect_url

    try:
        activity_id = await track_browser_activity(
            db=db,
            user_id=user_id,
            url=url,
            action=action,
            session_id=session_id,
            selector=selector,
            input_value=input_value,
            secrets_used=secrets_used,
            metadata=metadata,
        )

        logger.info(
            f"Browser activity tracked: user={user_id}, "
            f"action={action}, url={url[:50]}"
        )

        return activity_id

    except Exception as e:
        logger.error(
            f"Failed to track browser activity: {e}",
            exc_info=True,
        )
        raise


async def track_browser_navigation(
    db: AsyncSession,
    user_id: uuid.UUID,
    url: str,
    session_id: Optional[str] = None,
    status_code: Optional[int] = None,
) -> uuid.UUID:
    """
    Track browser navigation (page load).

    Args:
        db: Database session
        user_id: User who navigated
        url: Target URL
        session_id: Optional chat session ID
        status_code: HTTP status code

    Returns:
        Activity ID
    """
    return await track_browser_action(
        db=db,
        user_id=user_id,
        url=url,
        action="navigate",
        session_id=session_id,
        status_code=status_code,
    )


async def track_form_submission(
    db: AsyncSession,
    user_id: uuid.UUID,
    url: str,
    form_selector: str,
    session_id: Optional[str] = None,
    secrets_used: Optional[list[uuid.UUID]] = None,
) -> uuid.UUID:
    """
    Track form submission.

    Args:
        db: Database session
        user_id: User who submitted form
        url: Form URL
        form_selector: CSS selector for form element
        session_id: Optional chat session ID
        secrets_used: List of secret IDs used in form

    Returns:
        Activity ID
    """
    return await track_browser_action(
        db=db,
        user_id=user_id,
        url=url,
        action="submit",
        session_id=session_id,
        selector=form_selector,
        secrets_used=secrets_used,
    )


async def track_element_click(
    db: AsyncSession,
    user_id: uuid.UUID,
    url: str,
    selector: str,
    session_id: Optional[str] = None,
) -> uuid.UUID:
    """
    Track element click.

    Args:
        db: Database session
        user_id: User who clicked
        url: Page URL
        selector: CSS selector for clicked element
        session_id: Optional chat session ID

    Returns:
        Activity ID
    """
    return await track_browser_action(
        db=db,
        user_id=user_id,
        url=url,
        action="click",
        session_id=session_id,
        selector=selector,
    )
