# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Celery beat task: file attachment retention cleanup (GH#8995, MVA-3044).

Removes uploaded file attachments older than the configured TTL to prevent
unbounded storage growth in long-running deployments.
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict

from autobot_shared.logging_manager import get_logger
from celery_app import celery_app

logger = get_logger(__name__)

_DEFAULT_FILE_RETENTION_DAYS = 90


def _cleanup_expired_files(retention_days: int, dry_run: bool = False) -> Dict[str, int]:
    """Remove uploaded files older than retention_days.

    Args:
        retention_days: Number of days to retain files
        dry_run: If True, log what would be deleted without actually deleting

    Returns:
        Dict with "deleted_files", "deleted_bytes", and "errors" counts
    """
    # Get storage directories from conversation_file_manager pattern
    storage_base = Path(os.getenv("AUTOBOT_FILE_STORAGE_DIR", "data/uploads"))
    if not storage_base.exists():
        logger.info("File storage directory %s does not exist, skipping cleanup", storage_base)
        return {"deleted_files": 0, "deleted_bytes": 0, "errors": 0}

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    deleted_files = 0
    deleted_bytes = 0
    errors = 0

    try:
        # Walk through all files in storage directory
        for file_path in storage_base.rglob("*"):
            if not file_path.is_file():
                continue

            try:
                # Get file modification time
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
                file_size = file_path.stat().st_size

                if mtime < cutoff:
                    if dry_run:
                        logger.info(
                            "[DRY RUN] Would delete file: %s (age: %d days, size: %d bytes)",
                            file_path,
                            (datetime.now(timezone.utc) - mtime).days,
                            file_size,
                        )
                        deleted_files += 1
                        deleted_bytes += file_size
                    else:
                        file_path.unlink()
                        deleted_files += 1
                        deleted_bytes += file_size
                        logger.debug(
                            "Deleted file: %s (age: %d days, size: %d bytes)",
                            file_path,
                            (datetime.now(timezone.utc) - mtime).days,
                            file_size,
                        )

                        if deleted_files % 100 == 0:
                            logger.info("Deleted %d files so far...", deleted_files)

            except Exception as exc:
                errors += 1
                logger.error("Failed to process file %s: %s", file_path, exc)

        # Cleanup empty directories
        if not dry_run:
            for dir_path in sorted(storage_base.rglob("*"), key=lambda p: len(p.parts), reverse=True):
                if dir_path.is_dir() and not any(dir_path.iterdir()):
                    try:
                        dir_path.rmdir()
                        logger.debug("Removed empty directory: %s", dir_path)
                    except Exception as exc:
                        logger.debug("Could not remove directory %s: %s", dir_path, exc)

    except Exception as exc:
        errors += 1
        logger.error("File retention cleanup failed: %s", exc)

    logger.info(
        "File retention cleanup: deleted_files=%d, deleted_bytes=%d, errors=%d, retention_days=%d, dry_run=%s",
        deleted_files,
        deleted_bytes,
        errors,
        retention_days,
        dry_run,
    )
    return {
        "deleted_files": deleted_files,
        "deleted_bytes": deleted_bytes,
        "errors": errors,
    }


@celery_app.task(bind=True, name="tasks.cleanup_expired_files")
def cleanup_expired_files(self, retention_days: int = None, dry_run: bool = False) -> Dict[str, int]:
    """Remove uploaded file attachments older than retention_days (GH#8995, MVA-3044).

    Args:
        retention_days: Number of days to retain files. Defaults to
                        AUTOBOT_FILE_RETENTION_DAYS env var or 90 days.
        dry_run: If True, log what would be deleted without actually deleting.

    Returns:
        Dict with "deleted_files", "deleted_bytes", and "errors" counts.
    """
    if retention_days is None:
        retention_days = int(os.getenv("AUTOBOT_FILE_RETENTION_DAYS", _DEFAULT_FILE_RETENTION_DAYS))

    return _cleanup_expired_files(retention_days, dry_run)
