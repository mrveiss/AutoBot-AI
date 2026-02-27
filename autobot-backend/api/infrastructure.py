# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Infrastructure hosts API.

Provides the list of known AutoBot fleet VMs plus user-configured
infrastructure hosts (from secrets) for use by the chat terminal
and host-selection UI components.
"""

import logging
from typing import Any, Dict, List, Optional

from auth_middleware import get_current_user
from fastapi import APIRouter, Depends, Query

from autobot_shared.ssot_config import get_config

logger = logging.getLogger(__name__)
router = APIRouter(tags=["infrastructure"])

_config = get_config()

# Built-in fleet hosts with capabilities
_FLEET_HOSTS: List[Dict[str, Any]] = [
    {
        "id": "fleet-slm",
        "name": "autobot-slm",
        "host": _config.vm.slm,
        "ssh_port": 22,
        "description": "SLM Server (Fleet Manager)",
        "capabilities": ["ssh"],
    },
    {
        "id": "fleet-main",
        "name": "autobot-main",
        "host": _config.vm.main,
        "ssh_port": 22,
        "description": "Main Machine (Backend API + VNC)",
        "capabilities": ["ssh", "vnc"],
    },
    {
        "id": "fleet-frontend",
        "name": "autobot-frontend",
        "host": _config.vm.frontend,
        "ssh_port": 22,
        "description": "Frontend VM",
        "capabilities": ["ssh"],
    },
    {
        "id": "fleet-npu",
        "name": "autobot-npu-worker",
        "host": _config.vm.npu,
        "ssh_port": 22,
        "description": "NPU Worker VM",
        "capabilities": ["ssh"],
    },
    {
        "id": "fleet-redis",
        "name": "autobot-redis",
        "host": _config.vm.redis,
        "ssh_port": 22,
        "description": "Redis VM",
        "capabilities": ["ssh"],
    },
    {
        "id": "fleet-aistack",
        "name": "autobot-ai-stack",
        "host": _config.vm.aistack,
        "ssh_port": 22,
        "description": "AI Stack VM",
        "capabilities": ["ssh"],
    },
    {
        "id": "fleet-browser",
        "name": "autobot-browser",
        "host": _config.vm.browser,
        "ssh_port": 22,
        "description": "Browser VM",
        "capabilities": ["ssh"],
    },
]


def _load_secrets_hosts() -> List[Dict[str, Any]]:
    """Load infrastructure_host secrets and convert to host dicts."""
    try:
        from api.secrets import secrets_manager

        secrets = secrets_manager.list_secrets()
        hosts = []
        for s in secrets:
            if s.get("type") != "infrastructure_host":
                continue
            meta = s.get("metadata") or {}
            hosts.append(
                {
                    "id": s["id"],
                    "name": s.get("name", ""),
                    "host": meta.get("host", ""),
                    "ssh_port": meta.get("ssh_port", 22),
                    "vnc_port": meta.get("vnc_port"),
                    "username": meta.get("username", "root"),
                    "os": meta.get("os"),
                    "description": s.get("description", ""),
                    "capabilities": meta.get("capabilities", ["ssh"]),
                }
            )
        return hosts
    except Exception:
        logger.exception("Failed to load infrastructure host secrets")
        return []


@router.get("/hosts")
async def get_infrastructure_hosts(
    capability: Optional[str] = Query(
        None, description="Filter by capability (ssh, vnc)"
    ),
    chat_id: Optional[str] = Query(
        None, description="Associated chat session (unused, for context)"
    ),
    _user: Any = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return fleet hosts + user-configured hosts, filtered by capability."""
    # Merge secrets-based hosts (priority) with fleet defaults
    secrets_hosts = _load_secrets_hosts()
    seen = set()
    merged: List[Dict[str, Any]] = []

    for h in secrets_hosts:
        key = f"{h['host']}:{h['ssh_port']}"
        if key not in seen:
            seen.add(key)
            merged.append(h)

    for h in _FLEET_HOSTS:
        key = f"{h['host']}:{h['ssh_port']}"
        if key not in seen:
            seen.add(key)
            merged.append(h)

    if capability:
        merged = [h for h in merged if capability in h.get("capabilities", [])]

    return {"hosts": merged}
