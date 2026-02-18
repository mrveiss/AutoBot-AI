# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Role Registry Service (Issue #779).

Manages role definitions and provides default roles for code distribution.
"""

import logging
from typing import Dict, List, Optional

from models.database import Role, SyncType
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DEFAULT_ROLES = [
    {
        "name": "code-source",
        "display_name": "Code Source",
        "sync_type": None,
        "source_paths": [],
        "target_path": "",
        "auto_restart": False,
    },
    {
        "name": "backend",
        "display_name": "Backend API",
        "sync_type": SyncType.COMPONENT.value,
        "source_paths": ["autobot-backend/"],
        "target_path": "/opt/autobot",
        "systemd_service": "autobot-backend",
        "auto_restart": False,
        "health_check_port": 8001,
        "health_check_path": "/api/health",
    },
    {
        "name": "frontend",
        "display_name": "Frontend UI",
        "sync_type": SyncType.COMPONENT.value,
        "source_paths": ["autobot-frontend/"],
        "target_path": "/opt/autobot",
        "systemd_service": "autobot-frontend",
        "auto_restart": True,
        "health_check_port": 5173,
        "post_sync_cmd": "cd /opt/autobot/autobot-frontend && npm install",
    },
    {
        "name": "slm-server",
        "display_name": "SLM Server",
        "sync_type": SyncType.COMPONENT.value,
        "source_paths": ["autobot-slm-backend/", "autobot-slm-frontend/"],
        "target_path": "/opt/autobot",
        "systemd_service": "autobot-slm-backend",
        "auto_restart": False,
        "health_check_port": 8000,
        "health_check_path": "/api/health",
    },
    {
        "name": "slm-agent",
        "display_name": "SLM Agent",
        "sync_type": SyncType.COMPONENT.value,
        "source_paths": ["autobot-slm-backend/slm/agent/"],
        "target_path": "/opt/slm-agent",
        "systemd_service": "slm-agent",
        "auto_restart": True,
    },
    {
        "name": "npu-worker",
        "display_name": "NPU Worker",
        "sync_type": SyncType.PACKAGE.value,
        "source_paths": ["autobot-npu-worker/"],
        "target_path": "/opt/autobot/autobot-npu-worker",
        "auto_restart": False,
        "health_check_port": 8081,
    },
    {
        "name": "browser-service",
        "display_name": "Browser Automation",
        "sync_type": SyncType.COMPONENT.value,
        "source_paths": ["autobot-browser-worker/"],
        "target_path": "/opt/autobot/autobot-browser-worker",
        "systemd_service": "autobot-browser",
        "auto_restart": True,
        "health_check_port": 3000,
    },
]


async def seed_default_roles(db: AsyncSession) -> int:
    """Seed default roles if they don't exist."""
    created = 0
    for role_data in DEFAULT_ROLES:
        result = await db.execute(select(Role).where(Role.name == role_data["name"]))
        if not result.scalar_one_or_none():
            role = Role(**role_data)
            db.add(role)
            created += 1
            logger.info("Created default role: %s", role_data["name"])

    if created > 0:
        await db.commit()

    return created


async def get_role(db: AsyncSession, role_name: str) -> Optional[Role]:
    """Get role by name."""
    result = await db.execute(select(Role).where(Role.name == role_name))
    return result.scalar_one_or_none()


async def list_roles(db: AsyncSession) -> List[Role]:
    """List all roles."""
    result = await db.execute(select(Role).order_by(Role.name))
    return list(result.scalars().all())


async def get_role_definitions() -> List[Dict]:
    """Get lightweight role definitions for agents."""
    return [
        {
            "name": r["name"],
            "target_path": r["target_path"],
            "systemd_service": r.get("systemd_service"),
            "health_check_port": r.get("health_check_port"),
        }
        for r in DEFAULT_ROLES
        if r.get("target_path")
    ]
