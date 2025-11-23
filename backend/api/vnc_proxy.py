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
from typing import Any, Dict, Optional

import aiohttp
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse, Response

from src.constants.network_constants import NetworkConstants
from src.utils.error_boundaries import ErrorCategory, with_error_handling

router = APIRouter()
logger = logging.getLogger(__name__)

# VNC endpoints
VNC_ENDPOINTS = {
    "desktop": f"http://{NetworkConstants.MAIN_MACHINE_IP}:6080",
    "browser": f"http://{NetworkConstants.BROWSER_VM_IP}:6080",
}


async def record_observation(
    vnc_type: str, observation_type: str, data: Dict[str, Any]
):
    """
    Record VNC observation to MCP bridge for agent access

    This allows AutoBot's LLM agents to query VNC activity via MCP tools
    """
    try:
        observation = {
            "type": observation_type,
            "data": data,
        }

        # Post to VNC MCP bridge (non-blocking)
        backend_url = f"http://{NetworkConstants.MAIN_MACHINE_IP}:8001"
        async with aiohttp.ClientSession() as session:
            await session.post(
                f"{backend_url}/api/vnc/observations/{vnc_type}",
                json=observation,
                timeout=aiohttp.ClientTimeout(total=1),
            )
    except Exception as e:
        # Don't fail the proxy if observation recording fails
        logger.debug(f"Failed to record observation for {vnc_type}: {e}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_vnc_client",
    error_code_prefix="VNC_PROXY",
)
@router.get("/{vnc_type}/vnc.html")
async def get_vnc_client(vnc_type: str):
    """
    Serve noVNC client HTML for specified VNC type

    Args:
        vnc_type: 'desktop' or 'browser'
    """
    if vnc_type not in VNC_ENDPOINTS:
        raise HTTPException(status_code=404, detail=f"Unknown VNC type: {vnc_type}")

    endpoint = VNC_ENDPOINTS[vnc_type]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{endpoint}/vnc.html") as response:
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
        logger.error(f"Failed to fetch vnc.html from {endpoint}: {e}")
        raise HTTPException(status_code=503, detail=f"VNC server unavailable: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="proxy_vnc_assets",
    error_code_prefix="VNC_PROXY",
)
@router.get("/{vnc_type}/{path:path}")
async def proxy_vnc_assets(vnc_type: str, path: str):
    """
    Proxy noVNC static assets (JS, CSS, images, etc.)

    Args:
        vnc_type: 'desktop' or 'browser'
        path: Asset path (e.g., 'core/rfb.js', 'app/ui.js')
    """
    if vnc_type not in VNC_ENDPOINTS:
        raise HTTPException(status_code=404, detail=f"Unknown VNC type: {vnc_type}")

    endpoint = VNC_ENDPOINTS[vnc_type]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{endpoint}/{path}") as response:
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
        logger.error(f"Failed to fetch asset {path} from {endpoint}: {e}")
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
    logger.info(f"VNC WebSocket proxy connected: {vnc_type} → {ws_url}")

    # Record connection event for MCP
    await record_observation(
        vnc_type, "connection", {"endpoint": ws_url, "status": "connected"}
    )

    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(ws_url) as vnc_ws:

                async def forward_to_vnc():
                    """Forward messages from frontend to VNC server"""
                    try:
                        while True:
                            data = await websocket.receive()

                            if "bytes" in data:
                                await vnc_ws.send_bytes(data["bytes"])
                                # Agent observation point: could log binary data stats
                                logger.debug(
                                    f"[{vnc_type}] Frontend → VNC: {len(data['bytes'])} bytes"
                                )
                            elif "text" in data:
                                await vnc_ws.send_str(data["text"])
                                # Agent observation point: could log text messages
                                logger.debug(
                                    f"[{vnc_type}] Frontend → VNC: {data['text']}"
                                )
                            elif data.get("type") == "websocket.disconnect":
                                break
                    except WebSocketDisconnect:
                        logger.info(f"[{vnc_type}] Frontend disconnected")
                    except Exception as e:
                        logger.error(f"[{vnc_type}] Error forwarding to VNC: {e}")

                async def forward_from_vnc():
                    """Forward messages from VNC server to frontend"""
                    try:
                        async for msg in vnc_ws:
                            if msg.type == aiohttp.WSMsgType.BINARY:
                                await websocket.send_bytes(msg.data)
                                # Agent observation point: could analyze VNC protocol frames
                                logger.debug(
                                    f"[{vnc_type}] VNC → Frontend: {len(msg.data)} bytes"
                                )
                            elif msg.type == aiohttp.WSMsgType.TEXT:
                                await websocket.send_text(msg.data)
                                # Agent observation point: could log control messages
                                logger.debug(f"[{vnc_type}] VNC → Frontend: {msg.data}")
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                logger.error(
                                    f"[{vnc_type}] VNC WebSocket error: {vnc_ws.exception()}"
                                )
                                break
                    except Exception as e:
                        logger.error(f"[{vnc_type}] Error forwarding from VNC: {e}")

                # Run both forwarding tasks concurrently
                await asyncio.gather(
                    forward_to_vnc(),
                    forward_from_vnc(),
                    return_exceptions=True,
                )

    except aiohttp.ClientError as e:
        logger.error(f"[{vnc_type}] Failed to connect to VNC WebSocket: {e}")
        await websocket.close(code=1011, reason=f"VNC server unavailable: {str(e)}")
    except Exception as e:
        logger.error(f"[{vnc_type}] WebSocket proxy error: {e}")
        await websocket.close(code=1011, reason=str(e))
    finally:
        logger.info(f"VNC WebSocket proxy closed: {vnc_type}")
        # Record disconnection event for MCP
        await record_observation(vnc_type, "disconnection", {"status": "closed"})


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_vnc_status",
    error_code_prefix="VNC_PROXY",
)
@router.get("/{vnc_type}/status")
async def get_vnc_status(vnc_type: str):
    """
    Check if VNC server is accessible

    Args:
        vnc_type: 'desktop' or 'browser'
    """
    if vnc_type not in VNC_ENDPOINTS:
        raise HTTPException(status_code=404, detail=f"Unknown VNC type: {vnc_type}")

    endpoint = VNC_ENDPOINTS[vnc_type]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
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
        logger.error(f"Failed to check VNC status for {vnc_type}: {e}")
        return {
            "vnc_type": vnc_type,
            "endpoint": endpoint,
            "accessible": False,
            "error": str(e),
        }
