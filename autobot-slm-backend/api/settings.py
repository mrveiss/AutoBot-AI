# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Settings API Routes
"""

import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from models.database import Node, Setting
from models.schemas import SettingResponse, SettingUpdate
from pydantic import BaseModel
from services.auth import get_current_user, require_admin
from services.database import get_db
from services.playbook_executor import get_playbook_executor
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/settings", tags=["settings"])

DEFAULT_NTP_SERVERS = [
    "0.pool.ntp.org",
    "1.pool.ntp.org",
    "2.pool.ntp.org",
    "3.pool.ntp.org",
]


class TimeConfig(BaseModel):
    """Time synchronization configuration."""

    timezone: str = "UTC"
    ntp_servers: List[str] = DEFAULT_NTP_SERVERS


class TimeSyncRequest(BaseModel):
    """Request to trigger time sync on fleet nodes."""

    node_ids: Optional[List[str]] = None  # None = all nodes


class TimeSyncResult(BaseModel):
    """Result of a time sync operation."""

    success: bool
    message: str
    node_count: int
    output: Optional[str] = None


@router.get("/time/config", response_model=TimeConfig)
async def get_time_config(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> TimeConfig:
    """Get NTP and timezone configuration."""
    result = await db.execute(
        select(Setting).where(Setting.key.in_(["time_timezone", "time_ntp_servers"]))
    )
    rows = {s.key: s.value for s in result.scalars().all()}

    ntp_raw = rows.get("time_ntp_servers")
    ntp_servers = json.loads(ntp_raw) if ntp_raw else DEFAULT_NTP_SERVERS

    return TimeConfig(
        timezone=rows.get("time_timezone", "UTC"),
        ntp_servers=ntp_servers,
    )


async def _upsert_setting(db: AsyncSession, key: str, value: str, desc: str) -> None:
    """Insert or update a setting row.

    Helper for put_time_config (Issue #955).
    """
    result = await db.execute(select(Setting).where(Setting.key == key))
    row = result.scalar_one_or_none()
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value, description=desc))


@router.put("/time/config", response_model=TimeConfig)
async def put_time_config(
    config: TimeConfig,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_admin)],
) -> TimeConfig:
    """Save NTP and timezone configuration (admin only)."""
    await _upsert_setting(
        db, "time_timezone", config.timezone, "Default system timezone"
    )
    await _upsert_setting(
        db,
        "time_ntp_servers",
        json.dumps(config.ntp_servers),
        "NTP server list (JSON array)",
    )
    await db.commit()
    logger.info(
        "Time config updated: tz=%s ntp=%s", config.timezone, config.ntp_servers
    )
    return config


@router.post("/time/sync", response_model=TimeSyncResult)
async def sync_time(
    request: TimeSyncRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_admin)],
) -> TimeSyncResult:
    """Trigger Ansible time_sync role on fleet nodes (admin only)."""
    # Load current time config
    result = await db.execute(
        select(Setting).where(Setting.key.in_(["time_timezone", "time_ntp_servers"]))
    )
    rows = {s.key: s.value for s in result.scalars().all()}
    timezone = rows.get("time_timezone", "UTC")
    ntp_raw = rows.get("time_ntp_servers")
    ntp_servers = json.loads(ntp_raw) if ntp_raw else DEFAULT_NTP_SERVERS

    # Resolve target nodes for --limit
    limit: Optional[List[str]] = None
    node_count = 0
    if request.node_ids:
        node_result = await db.execute(
            select(Node).where(Node.node_id.in_(request.node_ids))
        )
        nodes = node_result.scalars().all()
        limit = [n.node_id for n in nodes]
        node_count = len(limit)
    else:
        node_result = await db.execute(select(Node))
        node_count = len(node_result.scalars().all())

    # Pass NTP servers as comma-separated string to avoid JSON shell-escaping issues.
    # The playbook splits on ',' to reconstruct the list.
    extra_vars = {
        "time_sync_timezone": timezone,
        "time_sync_ntp_servers_csv": ",".join(ntp_servers),
    }

    try:
        executor = get_playbook_executor()
        play_result = await executor.execute_playbook(
            playbook_name="playbooks/sync-time.yml",
            limit=limit,
            tags=["time_sync"],
            extra_vars=extra_vars,
        )
        logger.info(
            "Time sync complete: tz=%s nodes=%d success=%s",
            timezone,
            node_count,
            play_result.get("success"),
        )
        return TimeSyncResult(
            success=play_result.get("success", False),
            message=play_result.get("message", "Sync complete"),
            node_count=node_count,
            output=play_result.get("output"),
        )
    except Exception as exc:
        logger.error("Time sync failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Time sync failed: {exc}",
        ) from exc


@router.get("", response_model=List[SettingResponse])
async def list_settings(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> List[SettingResponse]:
    """List all settings."""
    result = await db.execute(select(Setting).order_by(Setting.key))
    settings = result.scalars().all()
    return [SettingResponse.model_validate(s) for s in settings]


@router.get("/{key}", response_model=SettingResponse)
async def get_setting(
    key: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> SettingResponse:
    """Get a setting by key."""
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()

    if not setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Setting not found",
        )

    return SettingResponse.model_validate(setting)


@router.put("/{key}", response_model=SettingResponse)
async def update_setting(
    key: str,
    setting_data: SettingUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_admin)],
) -> SettingResponse:
    """Update a setting (admin only)."""
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()

    if not setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Setting not found",
        )

    setting.value = setting_data.value
    if setting_data.description is not None:
        setting.description = setting_data.description

    await db.commit()
    await db.refresh(setting)

    logger.info("Setting updated: %s = %s", key, setting_data.value)
    return SettingResponse.model_validate(setting)


@router.post(
    "/{key}", response_model=SettingResponse, status_code=status.HTTP_201_CREATED
)
async def create_setting(
    key: str,
    setting_data: SettingUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_admin)],
) -> SettingResponse:
    """Create a new setting (admin only)."""
    result = await db.execute(select(Setting).where(Setting.key == key))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Setting already exists",
        )

    setting = Setting(
        key=key,
        value=setting_data.value,
        description=setting_data.description,
    )
    db.add(setting)
    await db.commit()
    await db.refresh(setting)

    logger.info("Setting created: %s = %s", key, setting_data.value)
    return SettingResponse.model_validate(setting)


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_setting(
    key: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_admin)],
) -> None:
    """Delete a setting (admin only)."""
    protected_keys = {
        "initialized",
        "monitoring_location",
        "prometheus_url",
        "grafana_url",
        "auto_remediate",
        "auto_restart_services",
        "auto_rollback",
        "heartbeat_timeout",
        "rollback_window_seconds",
    }

    if key in protected_keys:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete protected setting",
        )

    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()

    if not setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Setting not found",
        )

    await db.delete(setting)
    await db.commit()

    logger.info("Setting deleted: %s", key)
