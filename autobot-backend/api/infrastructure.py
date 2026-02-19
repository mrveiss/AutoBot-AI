# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Infrastructure hosts API.

Provides the list of known AutoBot fleet VMs for use by the chat terminal
and host-selection UI components. Authoritative source is SSOT config.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from autobot_shared.ssot_config import get_config
from backend.middleware.auth_middleware import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["infrastructure"])

_config = get_config()

# Capabilities each host supports
_HOST_CAPABILITIES: List[Dict[str, Any]] = [
    {
        "hostname": "autobot-slm",
        "ip": _config.vm.slm,
        "description": "SLM Server (Fleet Manager)",
        "capabilities": ["ssh"],
    },
    {
        "hostname": "autobot-main",
        "ip": _config.vm.main,
        "description": "Main Machine (Backend API + VNC)",
        "capabilities": ["ssh", "vnc"],
    },
    {
        "hostname": "autobot-frontend",
        "ip": _config.vm.frontend,
        "description": "Frontend VM",
        "capabilities": ["ssh"],
    },
    {
        "hostname": "autobot-npu-worker",
        "ip": _config.vm.npu,
        "description": "NPU Worker VM",
        "capabilities": ["ssh"],
    },
    {
        "hostname": "autobot-redis",
        "ip": _config.vm.redis,
        "description": "Redis VM",
        "capabilities": ["ssh"],
    },
    {
        "hostname": "autobot-ai-stack",
        "ip": _config.vm.aistack,
        "description": "AI Stack VM",
        "capabilities": ["ssh"],
    },
    {
        "hostname": "autobot-browser",
        "ip": _config.vm.browser,
        "description": "Browser VM",
        "capabilities": ["ssh"],
    },
]


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
    """Return list of known AutoBot fleet hosts, optionally filtered by capability."""
    hosts = _HOST_CAPABILITIES
    if capability:
        hosts = [h for h in hosts if capability in h["capabilities"]]

    return {
        "hosts": [
            {"hostname": h["hostname"], "ip": h["ip"], "description": h["description"]}
            for h in hosts
        ]
    }
