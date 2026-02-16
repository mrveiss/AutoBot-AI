# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
VNC WebSocket Proxy - Route VNC traffic through backend for agent observation

Provides WebSocket proxying for both VNC connections:
- /api/vnc-proxy/desktop → Main machine VNC (uses NetworkConstants.MAIN_MACHINE_IP)
- /api/vnc-proxy/browser → Browser VM VNC (uses NetworkConstants.BROWSER_VM_IP)

This allows the backend (where agent runs) to observe and log VNC traffic,
enabling the agent to see what users are viewing in real-time.
"""

import asyncio
import logging

import aiohttp
from auth_middleware import get_current_user
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.http_client import get_http_client
from backend.constants.network_constants import NetworkConstants
from backend.type_defs.common import Metadata

router = APIRouter()
logger = logging.getLogger(__name__)


async def _send_client_data_to_vnc(data: dict, vnc_ws, vnc_type: str) -> bool:
    """Send client WebSocket data to VNC server (Issue #315: extracted).

    Returns:
        True if data was sent successfully, False if should stop forwarding
    """
    if "bytes" in data:
        await vnc_ws.send_bytes(data["bytes"])
        logger.debug("[%s] Frontend → VNC: %s bytes", vnc_type, len(data["bytes"]))
        return True
    if "text" in data:
        await vnc_ws.send_str(data["text"])
        logger.debug("[%s] Frontend → VNC: %s", vnc_type, data["text"])
        return True
    if data.get("type") == "websocket.disconnect":
        return False
    return True


async def _send_vnc_msg_to_client(
    msg, websocket: WebSocket, vnc_ws, vnc_type: str
) -> bool:
    """Send VNC message to client WebSocket (Issue #315: extracted).

    Returns:
        True if should continue, False if should stop
    """
    if msg.type == aiohttp.WSMsgType.BINARY:
        await websocket.send_bytes(msg.data)
        logger.debug("[%s] VNC → Frontend: %s bytes", vnc_type, len(msg.data))
        return True
    if msg.type == aiohttp.WSMsgType.TEXT:
        await websocket.send_text(msg.data)
        logger.debug("[%s] VNC → Frontend: %s", vnc_type, msg.data)
        return True
    if msg.type == aiohttp.WSMsgType.ERROR:
        logger.error("[%s] VNC WebSocket error: %s", vnc_type, vnc_ws.exception())
        return False
    return True


async def _forward_client_to_vnc(websocket: WebSocket, vnc_ws, vnc_type: str) -> None:
    """Forward messages from frontend client to VNC server (Issue #315).

    Args:
        websocket: FastAPI WebSocket connection from client
        vnc_ws: aiohttp WebSocket connection to VNC server
        vnc_type: VNC type identifier for logging
    """
    try:
        while True:
            data = await websocket.receive()
            if not await _send_client_data_to_vnc(data, vnc_ws, vnc_type):
                break
    except WebSocketDisconnect:
        logger.info("[%s] Frontend disconnected", vnc_type)
    except Exception as e:
        logger.error("[%s] Error forwarding to VNC: %s", vnc_type, e)


async def _forward_vnc_to_client(websocket: WebSocket, vnc_ws, vnc_type: str) -> None:
    """Forward messages from VNC server to frontend client (Issue #315).

    Args:
        websocket: FastAPI WebSocket connection to client
        vnc_ws: aiohttp WebSocket connection from VNC server
        vnc_type: VNC type identifier for logging
    """
    try:
        async for msg in vnc_ws:
            if not await _send_vnc_msg_to_client(msg, websocket, vnc_ws, vnc_type):
                break
    except Exception as e:
        logger.error("[%s] Error forwarding from VNC: %s", vnc_type, e)


# VNC endpoints
VNC_ENDPOINTS = {
    "desktop": f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.VNC_PORT}",
    "browser": f"http://{NetworkConstants.BROWSER_VM_IP}:{NetworkConstants.VNC_PORT}",
}


async def record_observation(vnc_type: str, observation_type: str, data: Metadata):
    """
    Record VNC observation to MCP bridge for agent access

    This allows AutoBot's LLM agents to query VNC activity via MCP tools
    """
    try:
        observation = {
            "type": observation_type,
            "data": data,
        }

        # Post to VNC MCP bridge (non-blocking) using singleton HTTP client
        backend_url = (
            f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}"
        )
        http_client = get_http_client()
        async with await http_client.post(
            f"{backend_url}/api/vnc/observations/{vnc_type}",
            json=observation,
            timeout=aiohttp.ClientTimeout(total=1),
        ):
            pass  # Just fire and forget, we don't need the response
    except Exception as e:
        # Don't fail the proxy if observation recording fails
        logger.debug("Failed to record observation for %s: %s", vnc_type, e)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_vnc_client",
    error_code_prefix="VNC_PROXY",
)
@router.get("/{vnc_type}/vnc.html")
async def get_vnc_client(vnc_type: str, current_user: dict = Depends(get_current_user)):
    """
    Serve noVNC client HTML for specified VNC type

    Issue #744: Requires authenticated user.

    Args:
        vnc_type: 'desktop' or 'browser'
    """
    if vnc_type not in VNC_ENDPOINTS:
        raise HTTPException(status_code=404, detail=f"Unknown VNC type: {vnc_type}")

    endpoint = VNC_ENDPOINTS[vnc_type]

    try:
        http_client = get_http_client()
        async with await http_client.get(f"{endpoint}/vnc.html") as response:
            if response.status == 200:
                content = await response.read()
                return Response(
                    content=content,
                    media_type="text/html; charset=utf-8",
                    headers={
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                        "Pragma": "no-cache",
                        "Expires": "0",
                    },
                )
            else:
                raise HTTPException(
                    status_code=response.status,
                    detail=f"VNC server returned {response.status}",
                )
    except aiohttp.ClientError as e:
        logger.error("Failed to fetch vnc.html from %s: %s", endpoint, e)
        raise HTTPException(status_code=503, detail=f"VNC server unavailable: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="proxy_vnc_assets",
    error_code_prefix="VNC_PROXY",
)
@router.get("/{vnc_type}/{path:path}")
async def proxy_vnc_assets(
    vnc_type: str, path: str, current_user: dict = Depends(get_current_user)
):
    """
    Proxy noVNC static assets (JS, CSS, images, etc.)

    Issue #744: Requires authenticated user.

    Args:
        vnc_type: 'desktop' or 'browser'
        path: Asset path (e.g., 'core/rfb.js', 'app/ui.js')
    """
    if vnc_type not in VNC_ENDPOINTS:
        raise HTTPException(status_code=404, detail=f"Unknown VNC type: {vnc_type}")

    endpoint = VNC_ENDPOINTS[vnc_type]

    try:
        http_client = get_http_client()
        async with await http_client.get(f"{endpoint}/{path}") as response:
            if response.status == 200:
                content = await response.read()

                # Determine content type
                content_type = response.headers.get(
                    "Content-Type", "application/octet-stream"
                )

                return Response(
                    content=content,
                    media_type=content_type,
                    headers={
                        "Cache-Control": "public, max-age=3600",
                    },
                )
            else:
                raise HTTPException(
                    status_code=response.status,
                    detail=f"Asset not found: {path}",
                )
    except aiohttp.ClientError as e:
        logger.error("Failed to fetch asset %s from %s: %s", path, endpoint, e)
        raise HTTPException(status_code=503, detail=f"VNC server unavailable: {str(e)}")


@router.websocket("/{vnc_type}/websockify")
async def websocket_proxy(websocket: WebSocket, vnc_type: str):
    """
    WebSocket proxy for VNC connections

    Proxies WebSocket traffic between frontend and VNC server,
    allowing backend to observe and log VNC traffic for agent

    Args:
        vnc_type: 'desktop' or 'browser'
    """
    if vnc_type not in VNC_ENDPOINTS:
        await websocket.close(code=1003, reason=f"Unknown VNC type: {vnc_type}")
        return

    endpoint = VNC_ENDPOINTS[vnc_type]
    ws_url = endpoint.replace("http://", "ws://") + "/websockify"

    await websocket.accept()
    logger.info("VNC WebSocket proxy connected: %s → %s", vnc_type, ws_url)

    # Record connection event for MCP
    await record_observation(
        vnc_type, "connection", {"endpoint": ws_url, "status": "connected"}
    )

    try:
        http_client = get_http_client()
        session = await http_client.get_session()
        async with session.ws_connect(ws_url) as vnc_ws:
            # Run both forwarding tasks concurrently using extracted helpers (Issue #315)
            await asyncio.gather(
                _forward_client_to_vnc(websocket, vnc_ws, vnc_type),
                _forward_vnc_to_client(websocket, vnc_ws, vnc_type),
                return_exceptions=True,
            )

    except aiohttp.ClientError as e:
        logger.error("[%s] Failed to connect to VNC WebSocket: %s", vnc_type, e)
        await websocket.close(code=1011, reason=f"VNC server unavailable: {str(e)}")
    except Exception as e:
        logger.error("[%s] WebSocket proxy error: %s", vnc_type, e)
        await websocket.close(code=1011, reason=str(e))
    finally:
        logger.info("VNC WebSocket proxy closed: %s", vnc_type)
        # Record disconnection event for MCP
        await record_observation(vnc_type, "disconnection", {"status": "closed"})


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_vnc_status",
    error_code_prefix="VNC_PROXY",
)
@router.get("/{vnc_type}/status")
async def get_vnc_status(vnc_type: str, current_user: dict = Depends(get_current_user)):
    """
    Check if VNC server is accessible

    Issue #744: Requires authenticated user.

    Args:
        vnc_type: 'desktop' or 'browser'
    """
    if vnc_type not in VNC_ENDPOINTS:
        raise HTTPException(status_code=404, detail=f"Unknown VNC type: {vnc_type}")

    endpoint = VNC_ENDPOINTS[vnc_type]

    try:
        http_client = get_http_client()
        async with await http_client.get(
            f"{endpoint}/vnc.html", timeout=aiohttp.ClientTimeout(total=5)
        ) as response:
            accessible = response.status == 200
            return {
                "vnc_type": vnc_type,
                "endpoint": endpoint,
                "accessible": accessible,
                "status": response.status,
            }
    except Exception as e:
        logger.error("Failed to check VNC status for %s: %s", vnc_type, e)
        return {
            "vnc_type": vnc_type,
            "endpoint": endpoint,
            "accessible": False,
            "error": str(e),
        }
