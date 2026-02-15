# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Terminal Activity Tracking Integration

Issue #873 - Activity Tracking Integration Hooks (#608 Phase 5)

Integration hooks for tracking terminal command execution activities.
"""

import logging
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from utils.activity_tracker import track_terminal_activity

logger = logging.getLogger(__name__)


async def track_command_execution(
    db: AsyncSession,
    user_id: uuid.UUID,
    command: str,
    session_id: Optional[str] = None,
    working_directory: Optional[str] = None,
    exit_code: Optional[int] = None,
    output: Optional[str] = None,
    shell_type: str = "bash",
) -> uuid.UUID:
    """
    Track terminal command execution.

    Integration point for terminal handlers to record command activities.

    Args:
        db: Database session
        user_id: User who executed the command
        command: Shell command executed
        session_id: Optional chat session ID
        working_directory: Directory where command was executed
        exit_code: Command exit code (0 = success)
        output: Command output (stdout + stderr)
        shell_type: Shell type (bash, zsh, sh, etc.)

    Returns:
        Activity ID

    Example:
        >>> async with get_db_session() as db:
        ...     activity_id = await track_command_execution(
        ...         db=db,
        ...         user_id=uuid.UUID(...),
        ...         command="ls -la",
        ...         working_directory="/home/user",
        ...         exit_code=0,
        ...         output="file1.txt\\nfile2.txt",
        ...     )
    """
    metadata = {
        "shell": shell_type,
    }

    try:
        activity_id = await track_terminal_activity(
            db=db,
            user_id=user_id,
            command=command,
            session_id=session_id,
            working_directory=working_directory,
            exit_code=exit_code,
            output=output,
            metadata=metadata,
        )

        logger.info(
            f"Terminal activity tracked: user={user_id}, "
            f"command={command[:50]}, activity_id={activity_id}"
        )

        return activity_id

    except Exception as e:
        logger.error(
            f"Failed to track terminal activity: {e}",
            exc_info=True,
        )
        raise


async def track_pty_session_creation(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_id: Optional[str] = None,
    pty_id: Optional[str] = None,
    shell_type: str = "bash",
) -> uuid.UUID:
    """
    Track PTY session creation.

    Args:
        db: Database session
        user_id: User who created the session
        session_id: Optional chat session ID
        pty_id: PTY session identifier
        shell_type: Shell type

    Returns:
        Activity ID
    """
    metadata = {
        "shell": shell_type,
        "pty_id": pty_id,
        "event": "session_created",
    }

    activity_id = await track_terminal_activity(
        db=db,
        user_id=user_id,
        command=f"[PTY Session Created: {shell_type}]",
        session_id=session_id,
        metadata=metadata,
    )

    logger.info(f"PTY session creation tracked: user={user_id}, pty_id={pty_id}")

    return activity_id
