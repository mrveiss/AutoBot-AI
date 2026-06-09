# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Browser Automation Activity Tracking Integration

Issue #873 - Activity Tracking Integration Hooks (#608 Phase 5)

Integration hooks for tracking browser automation activities.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from utils.activity_tracker import track_browser_activity

logger = get_logger(__name__)


def _build_browser_action_metadata(
    status_code: int | None,
    redirect_url: str | None,
) -> dict[str, Any]:
    """Helper for track_browser_action. Ref: #1088."""
    metadata: dict[str, Any] = {}
    if status_code:
        metadata["status_code"] = status_code
    if redirect_url:
        metadata["redirect_url"] = redirect_url
    return metadata


async def _invoke_browser_activity_tracker(
    db: AsyncSession,
    user_id: uuid.UUID,
    url: str,
    action: str,
    session_id: str | None,
    selector: str | None,
    input_value: str | None,
    secrets_used: list[uuid.UUID] | None,
    metadata: dict[str, Any],
) -> uuid.UUID:
    """Helper for track_browser_action. Ref: #1088."""
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
        logger.info(f"Browser activity tracked: user={user_id}, " f"action={action}, url={url[:50]}")
        return activity_id
    except Exception as e:
        logger.error(
            f"Failed to track browser activity: {e}",
            exc_info=True,
        )
        raise


async def track_browser_action(
    db: AsyncSession,
    user_id: uuid.UUID,
    url: str,
    action: str,
    session_id: str | None = None,
    selector: str | None = None,
    input_value: str | None = None,
    secrets_used: list[uuid.UUID] | None = None,
    status_code: int | None = None,
    redirect_url: str | None = None,
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
    metadata = _build_browser_action_metadata(status_code, redirect_url)
    return await _invoke_browser_activity_tracker(
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


async def track_browser_navigation(
    db: AsyncSession,
    user_id: uuid.UUID,
    url: str,
    session_id: str | None = None,
    status_code: int | None = None,
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
    session_id: str | None = None,
    secrets_used: list[uuid.UUID] | None = None,
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
    session_id: str | None = None,
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
