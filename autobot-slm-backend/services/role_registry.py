# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Role Registry Service (Issue #779, #1129).

Manages role definitions and provides default roles for code distribution.
See docs/developer/ROLES.md for the authoritative role specification including
port conflicts and node placement constraints.
"""

import logging
import os
from typing import Dict, List, Optional

from models.database import Role, SyncType
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_BASE_DIR = os.environ.get("AUTOBOT_BASE_DIR", "/opt/autobot")
_SLM_AGENT_DIR = os.environ.get("SLM_AGENT_DIR", "/opt/autobot/autobot-slm-agent")

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SLM Manager roles  (.19 — separable)
# ---------------------------------------------------------------------------
_SLM_ROLES = [
    {
        "name": "slm-backend",
        "display_name": "SLM Backend",
        "sync_type": SyncType.COMPONENT.value,
        "source_paths": ["autobot-slm-backend/"],
        "target_path": _BASE_DIR,
        "systemd_service": "autobot-slm-backend",
        "auto_restart": True,
        "health_check_port": 8000,
        "health_check_path": "/api/health",
        "post_sync_cmd": (
            f"cd {_BASE_DIR}/autobot-slm-backend && "
            "pip install -r requirements.txt && "
            "alembic upgrade head"
        ),
        "required": True,
        "degraded_without": [],
        "ansible_playbook": "deploy-slm-manager.yml",
    },
    {
        "name": "slm-frontend",
        "display_name": "SLM Frontend",
        "sync_type": SyncType.COMPONENT.value,
        "source_paths": ["autobot-slm-frontend/"],
        "target_path": _BASE_DIR,
        "systemd_service": "nginx",
        "auto_restart": False,
        "health_check_port": 443,
        "post_sync_cmd": (
            f"cd {_BASE_DIR}/autobot-slm-frontend && npm install && npm run build"
        ),
        "required": True,
        "degraded_without": [],
        "ansible_playbook": "deploy-slm-manager.yml",
    },
    {
        "name": "slm-database",
        "display_name": "SLM Database",
        "sync_type": None,
        "source_paths": [],
        "target_path": "",
        "systemd_service": "postgresql",
        "auto_restart": False,
        "required": True,
        "degraded_without": [],
        "ansible_playbook": "playbooks/deploy_role.yml",
    },
    {
        "name": "slm-monitoring",
        "display_name": "SLM Monitoring",
        "sync_type": None,
        "source_paths": [],
        "target_path": "",
        "systemd_service": "prometheus",
        "auto_restart": False,
        "health_check_port": 9090,
        "health_check_path": "/-/healthy",
        "required": False,
        "degraded_without": ["Fleet metrics and alerting — monitoring unavailable"],
        "ansible_playbook": "deploy-monitoring.yml",
    },
]

# ---------------------------------------------------------------------------
# Main backend roles  (.20)
# ---------------------------------------------------------------------------
_BACKEND_ROLES = [
    {
        "name": "backend",
        "display_name": "Backend API",
        "sync_type": SyncType.COMPONENT.value,
        "source_paths": ["autobot-backend/"],
        "target_path": _BASE_DIR,
        "systemd_service": "autobot-backend",
        "auto_restart": True,
        "health_check_port": 8443,
        "health_check_path": "/api/health",
        "post_sync_cmd": (
            f"cd {_BASE_DIR}/autobot-backend && "
            "pip install -r requirements.txt && "
            "alembic upgrade head"
        ),
        "required": True,
        "degraded_without": [],
        "ansible_playbook": "deploy-backend.yml",
    },
    {
        "name": "celery",
        "display_name": "Celery Worker",
        "sync_type": SyncType.COMPONENT.value,
        "source_paths": ["autobot-backend/"],
        "target_path": _BASE_DIR,
        "systemd_service": "autobot-celery",
        "auto_restart": True,
        "required": True,
        "degraded_without": [],
        "ansible_playbook": "deploy-backend.yml",
    },
]

# ---------------------------------------------------------------------------
# Frontend role  (.21)
# ---------------------------------------------------------------------------
_FRONTEND_ROLES = [
    {
        "name": "frontend",
        "display_name": "Frontend UI",
        "sync_type": SyncType.COMPONENT.value,
        "source_paths": ["autobot-frontend/"],
        "target_path": _BASE_DIR,
        "systemd_service": "nginx",
        "auto_restart": False,
        "health_check_port": 443,
        "post_sync_cmd": (
            f"cd {_BASE_DIR}/autobot-frontend && npm install && npm run build"
        ),
        "required": True,
        "degraded_without": [],
        "ansible_playbook": "deploy-frontend.yml",
    },
]

# ---------------------------------------------------------------------------
# Database / infrastructure roles  (.23)
# ---------------------------------------------------------------------------
_DATABASE_ROLES = [
    {
        "name": "redis",
        "display_name": "Redis Stack",
        "sync_type": None,
        "source_paths": [],
        "target_path": "",
        "systemd_service": "redis-stack-server",
        "auto_restart": True,
        "required": True,
        "degraded_without": [],
        "ansible_playbook": "setup-redis-stack.yml",
    },
]

# ---------------------------------------------------------------------------
# AI Stack roles  (.24)
# ---------------------------------------------------------------------------
_AI_STACK_ROLES = [
    {
        "name": "ai-stack",
        "display_name": "AI Stack",
        "sync_type": SyncType.COMPONENT.value,
        "source_paths": ["autobot-ai-stack/"],
        "target_path": f"{_BASE_DIR}/autobot-ai-stack",
        "systemd_service": "autobot-ai-stack",
        "auto_restart": True,
        "health_check_port": 8080,
        "health_check_path": "/health",
        "post_sync_cmd": (
            f"cd {_BASE_DIR}/autobot-ai-stack && pip install -r requirements.txt"
        ),
        "required": True,
        "degraded_without": [],
        "ansible_playbook": "setup-ai-stack.yml",
    },
    {
        "name": "chromadb",
        "display_name": "ChromaDB",
        "sync_type": None,
        "source_paths": [],
        "target_path": "",
        "systemd_service": "autobot-chromadb",
        "auto_restart": True,
        "health_check_port": 8000,
        "health_check_path": "/api/v1/heartbeat",
        "required": True,
        "degraded_without": [],
        "ansible_playbook": "setup-ai-stack.yml",
    },
]

# ---------------------------------------------------------------------------
# Optional / portable roles
# ---------------------------------------------------------------------------
_OPTIONAL_ROLES = [
    {
        "name": "npu-worker",
        "display_name": "NPU Worker",
        "sync_type": SyncType.PACKAGE.value,
        "source_paths": ["autobot-npu-worker/"],
        "target_path": f"{_BASE_DIR}/autobot-npu-worker",
        "systemd_service": "autobot-npu-worker",
        "auto_restart": True,
        "health_check_port": 8081,
        "health_check_path": "/health",
        "post_sync_cmd": (
            f"cd {_BASE_DIR}/autobot-npu-worker && pip install -r requirements.txt"
        ),
        "required": False,
        "degraded_without": [
            "GPU inference offloading — backend falls back to local Ollama"
        ],
        "ansible_playbook": "setup-npu-worker.yml",
    },
    {
        "name": "tts-worker",
        "display_name": "TTS Worker",
        "sync_type": SyncType.COMPONENT.value,
        "source_paths": ["autobot-tts-worker/"],
        "target_path": f"{_BASE_DIR}/autobot-tts-worker",
        "systemd_service": "autobot-tts-worker",
        "auto_restart": True,
        "health_check_port": 8082,
        "health_check_path": "/health",
        "post_sync_cmd": (
            f"cd {_BASE_DIR}/autobot-tts-worker && pip install -r requirements.txt"
        ),
        "required": False,
        "degraded_without": ["Voice synthesis — TTS features unavailable"],
        "ansible_playbook": "playbooks/deploy_role.yml",
    },
    {
        "name": "browser-service",
        "display_name": "Browser Automation",
        "sync_type": SyncType.COMPONENT.value,
        "source_paths": ["autobot-browser-worker/"],
        "target_path": f"{_BASE_DIR}/autobot-browser-worker",
        "systemd_service": "autobot-playwright",
        "auto_restart": True,
        "health_check_port": 3000,
        "health_check_path": "/status",
        "post_sync_cmd": (f"cd {_BASE_DIR}/autobot-browser-worker && npm install"),
        "required": False,
        "degraded_without": ["Browser automation tasks — features degrade gracefully"],
        "ansible_playbook": "setup-browser-worker.yml",
    },
    {
        "name": "autobot-llm-cpu",
        "display_name": "LLM CPU Node",
        "sync_type": None,
        "source_paths": [],
        "target_path": "",
        "systemd_service": "ollama",
        "auto_restart": True,
        "health_check_port": 11434,
        "health_check_path": "/api/version",
        "required": False,
        "degraded_without": [
            "Local CPU inference — system falls back to cloud providers"
        ],
        "ansible_playbook": "playbooks/deploy_role.yml",
    },
    {
        "name": "autobot-llm-gpu",
        "display_name": "LLM GPU Node",
        "sync_type": None,
        "source_paths": [],
        "target_path": "",
        "systemd_service": "ollama",
        "auto_restart": True,
        "health_check_port": 11434,
        "health_check_path": "/api/version",
        "required": False,
        "degraded_without": [
            "Large model GPU inference — falls back to CPU models or cloud providers"
        ],
        "ansible_playbook": "playbooks/deploy_role.yml",
    },
]

# ---------------------------------------------------------------------------
# Infrastructure roles present on every node
# ---------------------------------------------------------------------------
_INFRA_ROLES = [
    {
        "name": "autobot-shared",
        "display_name": "Shared Library",
        "sync_type": SyncType.PACKAGE.value,
        "source_paths": ["autobot-shared/"],
        "target_path": f"{_BASE_DIR}/autobot-shared",
        "auto_restart": False,
        "post_sync_cmd": (f"cd {_BASE_DIR}/autobot-shared && pip install -e ."),
        "required": True,
        "degraded_without": [],
        "ansible_playbook": "deploy-shared.yml",
    },
    {
        "name": "slm-agent",
        "display_name": "SLM Agent",
        "sync_type": SyncType.COMPONENT.value,
        "source_paths": ["autobot-slm-backend/slm/agent/"],
        "target_path": _SLM_AGENT_DIR,
        "systemd_service": "slm-agent",
        "auto_restart": True,
        "post_sync_cmd": (f"cd {_SLM_AGENT_DIR} && pip install aiohttp psutil"),
        "required": True,
        "degraded_without": [],
        "ansible_playbook": "deploy-slm-agent.yml",
    },
]

DEFAULT_ROLES = (
    _SLM_ROLES
    + _BACKEND_ROLES
    + _FRONTEND_ROLES
    + _DATABASE_ROLES
    + _AI_STACK_ROLES
    + _OPTIONAL_ROLES
    + _INFRA_ROLES
)


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
    """Get lightweight role definitions for agents.

    Includes roles with either a target_path or a systemd_service so
    service-only roles (redis, chromadb, postgresql) are also detected.
    """
    return [
        {
            "name": r["name"],
            "target_path": r.get("target_path", ""),
            "systemd_service": r.get("systemd_service"),
            "health_check_port": r.get("health_check_port"),
            "required": r.get("required", False),
        }
        for r in DEFAULT_ROLES
        if r.get("target_path") or r.get("systemd_service")
    ]
