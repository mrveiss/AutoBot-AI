# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Process Management API (#1406)

Endpoints for spawning background processes, querying their status,
streaming logs, sending signals, and listing processes per agent.
"""

import logging
import os
from typing import List, Optional

from auth_middleware import get_current_user
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from services.process_adapter_service import ProcessAdapterService

logger = logging.getLogger(__name__)
router = APIRouter()

# Module-level singleton; initialised by application lifespan or DI.
_process_svc: Optional[ProcessAdapterService] = None


def set_process_adapter_service(svc: ProcessAdapterService) -> None:
    """Register the ProcessAdapterService singleton (#1406)."""
    global _process_svc
    _process_svc = svc


def _get_service() -> ProcessAdapterService:
    """Return the active ProcessAdapterService or raise 503 (#1406)."""
    if _process_svc is None:
        raise HTTPException(
            status_code=503, detail="Process adapter service unavailable"
        )
    return _process_svc


# -- Request / Response schemas --------------------------------------------


class SpawnRequest(BaseModel):
    """Body for POST /processes/spawn (#1406)."""

    agent_id: str = Field(..., description="Agent that owns the process")
    command: str = Field(..., description="Executable path or name")
    args: List[str] = Field(default_factory=list, description="Command arguments")
    timeout_seconds: int = Field(default=300, ge=1, le=86400)
    task_id: Optional[str] = Field(default=None, description="Optional parent task ID")


class SignalRequest(BaseModel):
    """Body for POST /processes/{process_id}/signal (#1406)."""

    signal: str = Field(..., description="Signal name: SIGTERM or SIGKILL")


class SpawnResponse(BaseModel):
    """Response for a successful spawn (#1406)."""

    process_id: str
    status: str
    message: str


# -- Endpoints -------------------------------------------------------------


@router.post("/processes/spawn", response_model=SpawnResponse)
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


@router.get("/processes/{process_id}")
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


@router.get("/processes/{process_id}/logs")
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


@router.post("/processes/{process_id}/signal")
async def signal_process(
    process_id: str,
    body: SignalRequest,
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Send a POSIX signal to a running process (#1406)."""
    svc = _get_service()
    try:
        delivered = await svc.signal_process(process_id, body.signal)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not delivered:
        raise HTTPException(
            status_code=409,
            detail=f"Process {process_id!r} is not running or already exited",
        )
    return JSONResponse(
        status_code=200,
        content={"process_id": process_id, "signal": body.signal, "delivered": True},
    )


@router.get("/agents/{agent_id}/processes")
async def list_agent_processes(
    agent_id: str,
    status: Optional[str] = Query(default=None, description="Filter by status"),
    limit: int = Query(default=20, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """List recent processes for an agent with optional status filter (#1406)."""
    svc = _get_service()
    processes = await svc.get_agent_processes(
        agent_id=agent_id, status_filter=status, limit=limit
    )
    return JSONResponse(
        status_code=200,
        content={"agent_id": agent_id, "processes": processes, "total": len(processes)},
    )


# -- Internal helpers ------------------------------------------------------


def _read_log_file(log_path: str) -> str:
    """Read a log file from disk and return its content (#1406)."""
    try:
        with open(log_path, encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        logger.warning("Could not read log file %s: %s", log_path, exc)
        return f"Log file unavailable: {exc}"
