# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Read-only status of one secrets-store backup, for the backend's verifier (#18281).

The backend's destructive secrets actions (e.g. the OAuth bundle strip) must not run
on unverified text. This route lets them ask the SLM -- the owner of the backup record
and the artifact -- whether a referenced backup exists, completed, is a secrets backup,
and still matches its checksum on disk. It returns facts only; the age and policy
decision stays with the caller. Mounted behind ``require_service_management_or_internal``
so the backend authenticates with ``X-Internal-API-Key`` like the node agent does.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import Backup, BackupServiceType, BackupStatus
from services.backup import backup_service
from services.database import get_db

router = APIRouter(prefix="/stateful", tags=["stateful"])


class SecretsBackupStatus(BaseModel):
    """What the verifier needs to decide, and nothing else (no path, no checksum)."""

    status: str | None
    service_type: str | None
    completed_at: str | None
    integrity_ok: bool


async def _integrity_ok(backup: Backup) -> bool:
    """Re-checksum the stored file; only a completed secrets backup with a stored checksum can pass."""
    if backup.status != BackupStatus.COMPLETED.value or backup.service_type != BackupServiceType.SECRETS.value:
        return False
    if not backup.checksum:
        return False
    result = await backup_service.verify_backup_integrity(backup.backup_id)
    return bool(result.get("valid")) and "warning" not in result


@router.get("/secrets-backups/{backup_id}", response_model=SecretsBackupStatus)
async def get_secrets_backup_status(
    backup_id: str, db: Annotated[AsyncSession, Depends(get_db)]
) -> SecretsBackupStatus:
    """Facts about one backup: its status, type, completion time and on-disk integrity."""
    result = await db.execute(select(Backup).where(Backup.backup_id == backup_id))
    backup = result.scalar_one_or_none()
    if backup is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found")
    return SecretsBackupStatus(
        status=backup.status,
        service_type=backup.service_type,
        completed_at=backup.completed_at.isoformat() if backup.completed_at else None,
        integrity_ok=await _integrity_ok(backup),
    )
