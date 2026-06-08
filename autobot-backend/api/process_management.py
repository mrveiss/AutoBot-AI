# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Process Management API (#1406)

Endpoints for spawning background processes, querying their status,
streaming logs, sending signals, and listing processes per agent.
"""

import os

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket
from fastapi.responses import JSONResponse, PlainTextResponse

from api.schemas_common import DataResponse
from api.schemas_system import (
    AgentProcessesData,
    ProcessSignalData,
    ProcessStatusData,
    SignalRequest,
    SpawnRequest,
    SpawnResponse,
)
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.error_utils import safe_http_detail
from autobot_shared.logging_manager import get_logger
from constants.threshold_constants import TimingConstants
from services.process_adapter_service import ProcessAdapterService

logger = get_logger(__name__)
router = APIRouter()

# Module-level singleton; initialised by application lifespan or DI.
_process_svc: ProcessAdapterService | None = None


def set_process_adapter_service(svc: ProcessAdapterService) -> None:
    """Register the ProcessAdapterService singleton (#1406)."""
    global _process_svc
    _process_svc = svc


def _get_service() -> ProcessAdapterService:
    """Return the active ProcessAdapterService or raise 503 (#1406)."""
    if _process_svc is None:
        raise HTTPException(status_code=503, detail="Process adapter service unavailable")
    return _process_svc


# -- Endpoints -------------------------------------------------------------


@router.post("/processes/spawn", response_model=SpawnResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="spawn_process",
    error_code_prefix="PROCESS_MANAGEMENT",
)
async def spawn_process(
    body: SpawnRequest,
    current_user: dict = Depends(get_current_user),
) -> SpawnResponse:
    """Start a new background process for an agent (#1406)."""
    svc = _get_service()
    process_id = await svc.spawn_process(
        agent_id=body.agent_id,
        command=body.command,
        args=body.args,
        timeout_seconds=body.timeout_seconds,
        task_id=body.task_id,
    )
    logger.info("Spawned process %s for agent %s", process_id, body.agent_id)
    return SpawnResponse(
        process_id=process_id,
        status="queued",
        message="Process queued for execution",
    )


@router.get("/processes/{process_id}", response_model=DataResponse[ProcessStatusData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_process_status",
    error_code_prefix="PROCESS_MANAGEMENT",
)
async def get_process_status(
    process_id: str,
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Return status and log excerpt for a process (#1406)."""
    svc = _get_service()
    data = await svc.get_process_status(process_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Process {process_id!r} not found")
    return JSONResponse(status_code=200, content=data)


@router.get("/processes/{process_id}/logs", response_model=None)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_process_logs",
    error_code_prefix="PROCESS_MANAGEMENT",
)
async def get_process_logs(
    process_id: str,
    current_user: dict = Depends(get_current_user),
) -> PlainTextResponse:
    """Return the full log output for a completed process (#1406)."""
    svc = _get_service()
    data = await svc.get_process_status(process_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Process {process_id!r} not found")
    log_path = data.get("log_path")
    if not log_path or not os.path.isfile(log_path):
        return PlainTextResponse(content=data.get("log_excerpt") or "", status_code=200)
    return PlainTextResponse(content=_read_log_file(log_path), status_code=200)


@router.post("/processes/{process_id}/signal", response_model=DataResponse[ProcessSignalData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="signal_process",
    error_code_prefix="PROCESS_MANAGEMENT",
)
async def signal_process(
    process_id: str,
    body: SignalRequest,
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Send a POSIX signal to a running process (#1406)."""
    svc = _get_service()
    try:
        delivered = await svc.signal_process(process_id, body.signal)
    except ValueError:
        raise HTTPException(status_code=400, detail="Request failed")
    if not delivered:
        raise HTTPException(
            status_code=409,
            detail=f"Process {process_id!r} is not running or already exited",
        )
    return JSONResponse(
        status_code=200,
        content={"process_id": process_id, "signal": body.signal, "delivered": True},
    )


@router.get("/agents/{agent_id}/processes", response_model=DataResponse[AgentProcessesData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_agent_processes",
    error_code_prefix="PROCESS_MANAGEMENT",
)
async def list_agent_processes(
    agent_id: str,
    status: str | None = Query(default=None, description="Filter by status"),
    limit: int = Query(default=20, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """List recent processes for an agent with optional status filter (#1406)."""
    svc = _get_service()
    processes = await svc.get_agent_processes(agent_id=agent_id, status_filter=status, limit=limit)
    return JSONResponse(
        status_code=200,
        content={"agent_id": agent_id, "processes": processes, "total": len(processes)},
    )


@router.websocket("/processes/{process_id}/stream")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="stream_process_logs",
    error_code_prefix="PROCESS_MANAGEMENT",
)
async def stream_process_logs(
    websocket: WebSocket,
    process_id: str,
) -> None:
    """Stream log output for a running process via WebSocket (#1777).

    Tails the log file and pushes new lines to the client every 500ms.
    Closes when the process completes or the client disconnects.
    """
    import asyncio

    await websocket.accept()
    svc = _get_service()
    offset = 0
    try:
        while True:
            data = await svc.get_process_status(process_id)
            if data is None:
                await websocket.send_json({"error": "Process not found"})
                break
            log_path = data.get("log_path")
            if log_path and os.path.isfile(log_path):
                content = _read_log_file(log_path)
                if len(content) > offset:
                    await websocket.send_text(content[offset:])
                    offset = len(content)
            elif data.get("log_excerpt") and offset == 0:
                await websocket.send_text(data["log_excerpt"])
                offset = len(data["log_excerpt"])
            if data.get("status") in (
                "completed",
                "failed",
                "timed_out",
                "cancelled",
            ):
                await websocket.send_json({"done": True, "status": data["status"]})
                break
            await asyncio.sleep(TimingConstants.SHORT_DELAY)
    except Exception:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# -- Internal helpers ------------------------------------------------------


def _read_log_file(log_path: str) -> str:
    """Read a log file from disk and return its content (#1406)."""
    try:
        with open(log_path, encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        logger.warning("Could not read log file %s: %s", log_path, exc)
        return safe_http_detail(exc, "Log file unavailable")
