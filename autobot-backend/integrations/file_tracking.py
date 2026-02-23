# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
File Browser Activity Tracking Integration

Issue #873 - Activity Tracking Integration Hooks (#608 Phase 5)

Integration hooks for tracking file system operation activities.
"""

import logging
import uuid
from pathlib import Path
from typing import Optional

from backend.utils.activity_tracker import track_file_activity
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _resolve_file_type(path: str) -> Optional[str]:
    """Helper for track_file_operation. Ref: #1088."""
    file_type = None
    try:
        path_obj = Path(path)
        if path_obj.suffix:
            file_type = path_obj.suffix.lstrip(".")
    except Exception:  # nosec B110 - silently handle invalid paths
        logger.debug("Suppressed exception in try block", exc_info=True)
    return file_type


async def _call_track_file_activity(
    db: AsyncSession,
    user_id: uuid.UUID,
    operation: str,
    path: str,
    session_id: Optional[str],
    new_path: Optional[str],
    file_type: Optional[str],
    size_bytes: Optional[int],
) -> uuid.UUID:
    """Helper for track_file_operation. Ref: #1088."""
    try:
        activity_id = await track_file_activity(
            db=db,
            user_id=user_id,
            operation=operation,
            path=path,
            session_id=session_id,
            new_path=new_path,
            file_type=file_type,
            size_bytes=size_bytes,
        )
        logger.info(
            f"File activity tracked: user={user_id}, "
            f"operation={operation}, path={path[:50]}"
        )
        return activity_id
    except Exception as e:
        logger.error(
            f"Failed to track file activity: {e}",
            exc_info=True,
        )
        raise


async def track_file_operation(
    db: AsyncSession,
    user_id: uuid.UUID,
    operation: str,
    path: str,
    session_id: Optional[str] = None,
    new_path: Optional[str] = None,
    size_bytes: Optional[int] = None,
) -> uuid.UUID:
    """
    Track file system operation.

    Integration point for file API handlers to record file activities.

    Args:
        db: Database session
        user_id: User who performed the operation
        operation: Operation type (create, read, update, delete, rename, move)
        path: File or directory path
        session_id: Optional chat session ID
        new_path: New path for rename/move operations
        size_bytes: File size in bytes

    Returns:
        Activity ID

    Example:
        >>> async with get_db_session() as db:
        ...     activity_id = await track_file_operation(
        ...         db=db,
        ...         user_id=uuid.UUID(...),
        ...         operation="create",
        ...         path="/home/user/document.txt",
        ...         size_bytes=1024,
        ...     )
    """
    file_type = _resolve_file_type(path)
    return await _call_track_file_activity(
        db=db,
        user_id=user_id,
        operation=operation,
        path=path,
        session_id=session_id,
        new_path=new_path,
        file_type=file_type,
        size_bytes=size_bytes,
    )


async def track_file_upload(
    db: AsyncSession,
    user_id: uuid.UUID,
    path: str,
    size_bytes: int,
    session_id: Optional[str] = None,
    mime_type: Optional[str] = None,
) -> uuid.UUID:
    """
    Track file upload operation.

    Args:
        db: Database session
        user_id: User who uploaded the file
        path: File path where uploaded
        size_bytes: File size in bytes
        session_id: Optional chat session ID
        mime_type: MIME type of uploaded file

    Returns:
        Activity ID
    """
    metadata = {
        "mime_type": mime_type,
        "upload": True,
    }

    activity_id = await track_file_activity(
        db=db,
        user_id=user_id,
        operation="create",
        path=path,
        session_id=session_id,
        file_type=mime_type,
        size_bytes=size_bytes,
        metadata=metadata,
    )

    logger.info(
        f"File upload tracked: user={user_id}, " f"path={path[:50]}, size={size_bytes}"
    )

    return activity_id


async def track_file_download(
    db: AsyncSession,
    user_id: uuid.UUID,
    path: str,
    session_id: Optional[str] = None,
) -> uuid.UUID:
    """
    Track file download operation.

    Args:
        db: Database session
        user_id: User who downloaded the file
        path: File path being downloaded
        session_id: Optional chat session ID

    Returns:
        Activity ID
    """
    metadata = {
        "download": True,
    }

    activity_id = await track_file_activity(
        db=db,
        user_id=user_id,
        operation="read",
        path=path,
        session_id=session_id,
        metadata=metadata,
    )

    logger.info(f"File download tracked: user={user_id}, path={path[:50]}")

    return activity_id
