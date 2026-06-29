# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Celery beat task: file attachment retention cleanup (GH#8995).

Removes uploaded file attachments older than the configured TTL.

Safe defaults: period=0 → task is a no-op.  Nothing is deleted unless
AUTOBOT_FILE_RETENTION_DAYS is set to a positive integer.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config as ssot_config
from celery_app import celery_app
from services.audit.audit import AuditCategory, AuditEvent
from services.audit.audit import emit as audit_emit

logger = get_logger(__name__)

# Module-level constant — reads env at import time (cache.py pattern)
_FILE_RETENTION_DAYS = ssot_config.file_retention_days
_STORAGE_BASE = Path(ssot_config.misc.chats_directory or "data") / "uploads"


def _emit_deletion_audit(file_path: str, extra: Dict[str, Any]) -> None:
    """Fire-and-forget audit event for a file retention deletion."""
    audit_emit(
        AuditEvent(
            category=AuditCategory.SECURITY,
            action="retention_purge",
            actor_id="system:retention_worker",
            resource_type="file_attachment",
            resource_id=file_path,
            metadata=extra,
        )
    )


def _cleanup_expired_files(retention_days: int, dry_run: bool = False) -> Dict[str, int]:
    """Remove uploaded files older than retention_days.

    Idempotent: files already deleted are silently skipped.
    Returns counts for deleted_files, deleted_bytes, errors.
    """
    if retention_days <= 0:
        logger.info("File retention disabled (retention_days=%d), skipping.", retention_days)
        return {"deleted_files": 0, "deleted_bytes": 0, "errors": 0}

    storage_base = _STORAGE_BASE
    if not storage_base.exists():
        logger.info("File storage dir %s does not exist — nothing to purge.", storage_base)
        return {"deleted_files": 0, "deleted_bytes": 0, "errors": 0}

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    deleted_files = 0
    deleted_bytes = 0
    errors = 0

    for file_path in storage_base.rglob("*"):
        if not file_path.is_file():
            continue
        try:
            stat = file_path.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            if mtime >= cutoff:
                continue

            size = stat.st_size
            age_days = (datetime.now(timezone.utc) - mtime).days

            if dry_run:
                logger.info("[DRY RUN] Would delete %s (age=%dd, size=%d)", file_path, age_days, size)
                deleted_files += 1
                deleted_bytes += size
            else:
                file_path.unlink()
                _emit_deletion_audit(
                    str(file_path),
                    {"age_days": age_days, "size_bytes": size, "retention_days": retention_days},
                )
                deleted_files += 1
                deleted_bytes += size
                logger.debug("Deleted %s (age=%dd, size=%d)", file_path, age_days, size)
        except FileNotFoundError:
            pass  # Already deleted — idempotent
        except Exception as exc:
            errors += 1
            logger.error("Error processing %s: %s", file_path, exc)

    # Remove empty directories (best-effort)
    if not dry_run:
        for dir_path in sorted(storage_base.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if dir_path.is_dir() and not any(dir_path.iterdir()):
                try:
                    dir_path.rmdir()
                except Exception:
                    pass

    logger.info(
        "File retention: deleted_files=%d deleted_bytes=%d errors=%d retention_days=%d dry_run=%s",
        deleted_files,
        deleted_bytes,
        errors,
        retention_days,
        dry_run,
    )
    return {"deleted_files": deleted_files, "deleted_bytes": deleted_bytes, "errors": errors}


@celery_app.task(bind=True, name="tasks.cleanup_expired_files")
def cleanup_expired_files(self, retention_days: int = None, dry_run: bool = False) -> Dict[str, int]:
    """Remove uploaded file attachments older than retention_days (GH#8995).

    retention_days defaults to AUTOBOT_FILE_RETENTION_DAYS (0 = disabled).
    dry_run=True logs what would be deleted without making changes.
    """
    if retention_days is None:
        retention_days = _FILE_RETENTION_DAYS
    return _cleanup_expired_files(retention_days, dry_run)
