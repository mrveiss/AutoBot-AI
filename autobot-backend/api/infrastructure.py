# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Infrastructure hosts API.

Provides user-configured infrastructure hosts (from secrets) for use
by the chat terminal and host-selection UI components.

Issue #1310: Fleet/system VMs removed — they belong in SLM only.
"""

import logging
from typing import Any, Dict, List, Optional

from auth_middleware import get_current_user
from fastapi import APIRouter, Depends, Query

logger = logging.getLogger(__name__)
router = APIRouter(tags=["infrastructure"])

# Issue #1310: Fleet hosts removed from main UI.
# System infrastructure VMs should only appear in SLM.
# This endpoint now returns only user-configured hosts from secrets.


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
    """Return user-configured hosts from secrets, filtered by capability.

    Issue #1310: Fleet/system hosts removed — they belong in SLM only.
    Only hosts explicitly added by the user via Secrets are returned.
    """
    hosts = _load_secrets_hosts()

    if capability:
        hosts = [h for h in hosts if capability in h.get("capabilities", [])]

    return {"hosts": hosts}
