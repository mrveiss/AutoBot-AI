# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Activity Tracking Utility

Issue #873 - Activity Tracking Integration Hooks (#608 Phase 5)

Centralized utility for tracking user activities across all UI components.
Provides async, non-blocking activity recording with secret usage detection.
"""

import logging
import re
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.activities import (
    BrowserActivityModel,
    DesktopActivityModel,
    FileActivityModel,
    SecretUsageModel,
    TerminalActivityModel,
)

logger = logging.getLogger(__name__)


# Secret detection patterns
SECRET_PATTERNS = [
    re.compile(r"--password[=\s]+[^\s]+", re.IGNORECASE),
    re.compile(r"-p\s+[^\s]+"),
    re.compile(r"export\s+\w*(?:PASSWORD|TOKEN|KEY|SECRET)\w*=", re.IGNORECASE),
    re.compile(r"(?:api[_-]?key|token|secret)[=:\s]+", re.IGNORECASE),
]


def _detect_secrets_in_command(command: str) -> bool:
    """Helper for detecting potential secret usage in commands.

    Helper for detect_secret_usage (Issue #873).
    """
    for pattern in SECRET_PATTERNS:
        if pattern.search(command):
            return True
    return False


def detect_secret_usage(
    text: str,
    known_secret_ids: Optional[list[uuid.UUID]] = None,
) -> list[uuid.UUID]:
    """
    Detect potential secret usage in text.

    Args:
        text: Command, URL, or input text to analyze
        known_secret_ids: Optional list of secret IDs to check against

    Returns:
        List of secret IDs detected in text
    """
    detected = []

    # Check known secrets if provided
    if known_secret_ids:
        detected.extend(known_secret_ids)

    # Pattern-based detection for unknown secrets
    if _detect_secrets_in_command(text):
        # Log detection but don't create phantom secrets
        logger.info(f"Potential secret usage detected in activity: {text[:50]}...")

    return detected


async def track_terminal_activity(
    db: AsyncSession,
    user_id: uuid.UUID,
    command: str,
    session_id: Optional[str] = None,
    working_directory: Optional[str] = None,
    exit_code: Optional[int] = None,
    output: Optional[str] = None,
    secrets_used: Optional[list[uuid.UUID]] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> uuid.UUID:
    """
    Track terminal command execution activity.

    Args:
        db: Database session
        user_id: User who executed the command
        command: Shell command executed
        session_id: Optional chat session ID
        working_directory: Directory where command was executed
        exit_code: Command exit code
        output: Command output
        secrets_used: List of secret IDs used
        metadata: Additional metadata

    Returns:
        Activity ID
    """
    if secrets_used is None:
        secrets_used = detect_secret_usage(command)

    activity = TerminalActivityModel(
        user_id=user_id,
        session_id=session_id,
        command=command,
        working_directory=working_directory,
        exit_code=exit_code,
        output=output,
        secrets_used=secrets_used,
        metadata=metadata or {},
        timestamp=datetime.utcnow(),
    )

    db.add(activity)
    await db.commit()
    await db.refresh(activity)

    logger.info(
        f"Tracked terminal activity: user={user_id}, "
        f"command={command[:50]}, secrets={len(secrets_used)}"
    )

    # Track secret usage
    for secret_id in secrets_used:
        await _track_secret_usage(
            db, secret_id, user_id, "terminal", activity.id, session_id
        )

    return activity.id


async def track_file_activity(
    db: AsyncSession,
    user_id: uuid.UUID,
    operation: str,
    path: str,
    session_id: Optional[str] = None,
    new_path: Optional[str] = None,
    file_type: Optional[str] = None,
    size_bytes: Optional[int] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> uuid.UUID:
    """
    Track file system operation activity.

    Args:
        db: Database session
        user_id: User who performed the operation
        operation: Operation type (create, read, update, delete, rename, move)
        path: File or directory path
        session_id: Optional chat session ID
        new_path: New path for rename/move operations
        file_type: File MIME type or extension
        size_bytes: File size in bytes
        metadata: Additional metadata

    Returns:
        Activity ID
    """
    activity = FileActivityModel(
        user_id=user_id,
        session_id=session_id,
        operation=operation,
        path=path,
        new_path=new_path,
        file_type=file_type,
        size_bytes=size_bytes,
        metadata=metadata or {},
        timestamp=datetime.utcnow(),
    )

    db.add(activity)
    await db.commit()
    await db.refresh(activity)

    logger.info(
        f"Tracked file activity: user={user_id}, "
        f"operation={operation}, path={path[:50]}"
    )

    return activity.id


async def track_browser_activity(
    db: AsyncSession,
    user_id: uuid.UUID,
    url: str,
    action: str,
    session_id: Optional[str] = None,
    selector: Optional[str] = None,
    input_value: Optional[str] = None,
    secrets_used: Optional[list[uuid.UUID]] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> uuid.UUID:
    """
    Track browser automation activity.

    Args:
        db: Database session
        user_id: User who performed the action
        url: Target URL
        action: Action type (navigate, click, type, submit, scroll)
        session_id: Optional chat session ID
        selector: CSS selector for targeted element
        input_value: Value entered (for type/submit actions)
        secrets_used: List of secret IDs used
        metadata: Additional metadata

    Returns:
        Activity ID
    """
    if secrets_used is None and input_value:
        secrets_used = detect_secret_usage(input_value)

    activity = BrowserActivityModel(
        user_id=user_id,
        session_id=session_id,
        url=url,
        action=action,
        selector=selector,
        input_value=input_value,
        secrets_used=secrets_used or [],
        metadata=metadata or {},
        timestamp=datetime.utcnow(),
    )

    db.add(activity)
    await db.commit()
    await db.refresh(activity)

    logger.info(
        f"Tracked browser activity: user={user_id}, "
        f"action={action}, url={url[:50]}, secrets={len(secrets_used or [])}"
    )

    # Track secret usage
    for secret_id in secrets_used or []:
        await _track_secret_usage(
            db, secret_id, user_id, "browser", activity.id, session_id
        )

    return activity.id


async def track_desktop_activity(
    db: AsyncSession,
    user_id: uuid.UUID,
    action: str,
    session_id: Optional[str] = None,
    coordinates: Optional[tuple[int, int]] = None,
    window_title: Optional[str] = None,
    input_text: Optional[str] = None,
    screenshot_path: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
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
        user_id=user_id,
        session_id=session_id,
        action=action,
        coordinates=coordinates,
        window_title=window_title,
        input_text=input_text,
        screenshot_path=screenshot_path,
        metadata=metadata or {},
        timestamp=datetime.utcnow(),
    )

    db.add(activity)
    await db.commit()
    await db.refresh(activity)

    logger.info(f"Tracked desktop activity: user={user_id}, " f"action={action}")

    return activity.id


async def _track_secret_usage(
    db: AsyncSession,
    secret_id: uuid.UUID,
    user_id: uuid.UUID,
    activity_type: str,
    activity_id: uuid.UUID,
    session_id: Optional[str] = None,
    access_granted: bool = True,
    denial_reason: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    """
    Track secret usage for audit trail.

    Helper for track_terminal_activity and track_browser_activity (Issue #873).

    Args:
        db: Database session
        secret_id: ID of secret accessed
        user_id: User who accessed secret
        activity_type: Type of activity (terminal, browser, file, desktop)
        activity_id: ID of parent activity
        session_id: Optional chat session ID
        access_granted: Whether access was granted
        denial_reason: Reason for denial (if access_granted=False)
        metadata: Additional metadata
    """
    usage = SecretUsageModel(
        secret_id=secret_id,
        user_id=user_id,
        activity_type=activity_type,
        activity_id=activity_id,
        session_id=session_id,
        access_granted=access_granted,
        denial_reason=denial_reason,
        metadata=metadata or {},
        timestamp=datetime.utcnow(),
    )

    db.add(usage)
    await db.commit()

    logger.info(
        f"Tracked secret usage: secret={secret_id}, "
        f"user={user_id}, activity={activity_type}"
    )
