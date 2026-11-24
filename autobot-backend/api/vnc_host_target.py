# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Resolve the host a chat Desktop control acts on (#22145).

The target comes ONLY from the user's /secrets ``infrastructure_host`` entries,
through the one resolver terminal_ssh already uses
(``api.infrastructure.get_secrets_host``). A fleet node id, an unknown id or a
host without VNC is refused; there is no fallback to AutoBot's own display.
"""

import asyncio
from dataclasses import dataclass

from fastapi import HTTPException

from api.infrastructure import get_secrets_host
from api.infrastructure_host_rules import host_fields_detail, missing_host_fields
from api.vnc_handshake_bridge import get_vnc_password
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from constants.network_constants import NetworkConstants
from security.secrets_store_errors import SecretsStoreUnavailable
from security.vnc_rfb_auth import VncAuthError

logger = get_logger(__name__)

# Picker id of AutoBot's own desktop VM (owner 2026-11-24: the chat Desktop offers it next to the user's
# /secrets hosts). Distinct from any secret id; mirrored by DESKTOP_VM_HOST_ID in the frontend vnc-client.ts.
DESKTOP_VM_HOST_ID = "autobot-desktop-vm"
# The vnc_type under which the desktop VM's VNC password is registered (api/vnc_handshake_bridge.py).
DESKTOP_VM_VNC_TYPE = "desktop"

# Metadata key on the companion secret that holds a host's VNC password.
VNC_COMPANION_HOST_KEY = "vnc_host_id"

# Stable error code the UI maps to its own i18n text.
VNC_AUTH_MISSING = "vnc_credential_missing"
HOST_NOT_FOUND = "host_not_found"
HOST_VNC_UNAVAILABLE = "host_vnc_unavailable"


@dataclass(frozen=True)
class VncTarget:
    host_id: str
    address: str
    port: int
    password: bytes


def _read_vnc_password(host_id: str) -> bytes | None:
    """Blocking: the stored VNC password of *host_id* (a ``password`` secret linked by metadata), or None."""
    from api.secrets import secrets_manager

    for entry in secrets_manager.list_secrets():
        if entry.get("type") != "password":
            continue
        if (entry.get("metadata") or {}).get(VNC_COMPANION_HOST_KEY) != host_id:
            continue
        secret = secrets_manager.get_secret(entry["id"])
        if secret and secret.get("value"):
            return str(secret["value"]).encode("utf-8")
    return None


async def _vnc_password_for(host_id: str) -> bytes:
    """The host's VNC password, read off the event loop; fails closed with a stable error code when absent."""
    password = await asyncio.to_thread(_read_vnc_password, host_id)
    if password is None:
        raise HTTPException(
            status_code=422,
            detail={"code": VNC_AUTH_MISSING, "message": "No VNC password is stored for this host."},
        )
    return password


def _checked_host(host_id: str) -> dict:
    try:
        host = get_secrets_host(host_id) if host_id else None
    except SecretsStoreUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if host is None:
        raise HTTPException(
            status_code=404,
            detail={"code": HOST_NOT_FOUND, "message": "Host is not one of your /secrets infrastructure hosts"},
        )
    missing = missing_host_fields(host)
    if missing:
        raise HTTPException(status_code=422, detail=host_fields_detail(missing))
    if "vnc" not in host["capabilities"] or not host.get("vnc_port") or not host.get("host"):
        raise HTTPException(
            status_code=422,
            detail={"code": HOST_VNC_UNAVAILABLE, "message": "Host has no VNC capability or port in Secrets"},
        )
    return host


def resolve_host_id(host_id: str) -> str:
    """Validate that *host_id* is the desktop VM or a VNC-capable /secrets host; return it unchanged.

    Any other id (another fleet node, a stale or empty id) is refused with 404.
    """
    if host_id == DESKTOP_VM_HOST_ID:
        return host_id
    return _checked_host(host_id)["id"]


async def _desktop_vm_target() -> VncTarget:
    """The desktop VM: SSOT main-machine address, SSOT raw VNC port, and the vault's `desktop` password."""
    try:
        password = await get_vnc_password(DESKTOP_VM_VNC_TYPE)
    except VncAuthError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": VNC_AUTH_MISSING, "message": "No VNC password is registered for the desktop VM."},
        ) from exc
    return VncTarget(DESKTOP_VM_HOST_ID, NetworkConstants.MAIN_MACHINE_IP, config.port.vnc_server, password)


async def resolve_vnc_target(host_id: str) -> VncTarget:
    """Address, RFB port and password of the selected desktop VM or /secrets host."""
    if host_id == DESKTOP_VM_HOST_ID:
        return await _desktop_vm_target()
    host = _checked_host(host_id)
    return VncTarget(host["id"], host["host"], int(host["vnc_port"]), await _vnc_password_for(host["id"]))
