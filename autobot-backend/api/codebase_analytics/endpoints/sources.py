# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code source registry endpoints (#1133).

CRUD + sync + share for registered code sources.
Mount point: /api/analytics/codebase/sources (via router.py)
"""

import asyncio
import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

from ..source_models import (
    CodeSource,
    CodeSourceCreateRequest,
    CodeSourceUpdateRequest,
    SourceShareRequest,
    SourceStatus,
    SourceSyncResponse,
)
from ..source_storage import delete_source, get_source, list_sources, save_source

logger = logging.getLogger(__name__)

router = APIRouter()

_CODE_SOURCES_BASE = Path("/opt/autobot/data/code-sources")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_clone_path(source_id: str) -> str:
    """Return the canonical clone path for a source ID."""
    return str(_CODE_SOURCES_BASE / source_id)


async def _resolve_token(credential_id: str) -> Optional[str]:
    """Return the decrypted token value for a credential ID, or None."""
    try:
        from api.secrets import secrets_manager

        secret = await asyncio.to_thread(secrets_manager.get_secret, credential_id)
        return secret["value"] if secret else None
    except Exception as exc:
        logger.warning("Failed to resolve credential %s: %s", credential_id, exc)
        return None


def _build_clone_url(repo: str, token: Optional[str]) -> str:
    """Build a GitHub clone URL, injecting token if available."""
    if token:
        return f"https://{token}@github.com/{repo}"
    return f"https://github.com/{repo}"


async def _run_git_clone(url: str, dest: str, branch: str) -> str:
    """Clone a repo shallowly. Returns stderr on failure."""
    proc = await asyncio.create_subprocess_exec(
        "git",
        "clone",
        "--depth=1",
        "--branch",
        branch,
        url,
        dest,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        return stderr.decode("utf-8", errors="replace")
    return ""


async def _run_git_pull(clone_path: str) -> str:
    """Pull latest changes in an existing clone. Returns stderr on failure."""
    proc = await asyncio.create_subprocess_exec(
        "git",
        "-C",
        clone_path,
        "pull",
        "--ff-only",
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        return stderr.decode("utf-8", errors="replace")
    return ""


async def _do_sync(source: CodeSource) -> None:
    """Background task: clone/pull and update source status in Redis."""
    source.status = SourceStatus.SYNCING
    await save_source(source)

    try:
        clone_path = source.clone_path
        token = None
        if source.credential_id:
            token = await _resolve_token(source.credential_id)

        err = ""
        if source.source_type == "github" and source.repo:
            url = _build_clone_url(source.repo, token)
            if Path(clone_path).is_dir():
                err = await _run_git_pull(clone_path)
            else:
                Path(clone_path).mkdir(parents=True, exist_ok=True)
                err = await _run_git_clone(url, clone_path, source.branch)

        if err:
            source.status = SourceStatus.ERROR
            source.error_message = err[:500]
        else:
            source.status = SourceStatus.READY
            source.last_synced = datetime.now().isoformat()
            source.error_message = None
            await _trigger_indexing(source)

    except Exception as exc:
        logger.error("Sync failed for source %s: %s", source.id, exc)
        source.status = SourceStatus.ERROR
        source.error_message = str(exc)[:500]

    await save_source(source)


async def _trigger_indexing(source: CodeSource) -> None:
    """Queue an indexing job for the source's clone path (#1133)."""
    try:
        from ..scanner import (
            _active_tasks,
            _current_indexing_task_id,
            _index_queue,
            _tasks_lock,
            do_indexing_with_progress,
            indexing_tasks,
        )

        task_id = str(uuid.uuid4())
        async with _tasks_lock:
            if _current_indexing_task_id is None:
                indexing_tasks[task_id] = {"status": "running"}
                task = asyncio.create_task(
                    do_indexing_with_progress(task_id, source.clone_path)
                )
                _active_tasks[task_id] = task
            else:
                _index_queue.append(
                    {
                        "source_id": source.id,
                        "root_path": source.clone_path,
                        "queued_at": datetime.now().isoformat(),
                        "requested_by": "sync",
                    }
                )
    except Exception as exc:
        logger.warning("Could not trigger indexing for %s: %s", source.id, exc)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_sources",
    error_code_prefix="CODEBASE",
)
@router.get("/sources")
async def list_code_sources():
    """List all registered code sources."""
    sources = await list_sources()
    return JSONResponse({"sources": [s.model_dump() for s in sources]})


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_source",
    error_code_prefix="CODEBASE",
)
@router.post("/sources")
async def create_code_source(request: CodeSourceCreateRequest):
    """Register a new code source."""
    source = CodeSource(
        name=request.name,
        source_type=request.source_type,
        repo=request.repo,
        branch=request.branch,
        credential_id=request.credential_id,
        access=request.access,
    )
    if source.source_type == "github" and source.repo:
        source.clone_path = _make_clone_path(source.id)
    await save_source(source)
    logger.info("Created code source %s (%s)", source.id, source.name)
    return JSONResponse(source.model_dump(), status_code=201)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_source",
    error_code_prefix="CODEBASE",
)
@router.get("/sources/{source_id}")
async def get_code_source(source_id: str):
    """Retrieve a code source by ID."""
    source = await get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")
    return JSONResponse(source.model_dump())


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_source",
    error_code_prefix="CODEBASE",
)
@router.put("/sources/{source_id}")
async def update_code_source(source_id: str, request: CodeSourceUpdateRequest):
    """Update an existing code source."""
    source = await get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")
    if request.name is not None:
        source.name = request.name
    if request.branch is not None:
        source.branch = request.branch
    if request.credential_id is not None:
        source.credential_id = request.credential_id
    if request.access is not None:
        source.access = request.access
    await save_source(source)
    return JSONResponse(source.model_dump())


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_source",
    error_code_prefix="CODEBASE",
)
@router.delete("/sources/{source_id}")
async def delete_code_source(source_id: str):
    """Delete a code source and remove its clone directory if present."""
    source = await get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")
    if source.clone_path and Path(source.clone_path).exists():
        shutil.rmtree(source.clone_path, ignore_errors=True)
    ok = await delete_source(source_id)
    logger.info("Deleted code source %s", source_id)
    return JSONResponse({"success": ok, "source_id": source_id})


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="sync_source",
    error_code_prefix="CODEBASE",
)
@router.post("/sources/{source_id}/sync")
async def sync_code_source(source_id: str):
    """Trigger an async clone/pull for a code source."""
    source = await get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")
    if source.source_type == "local":
        raise HTTPException(
            status_code=400, detail="Local sources do not require syncing"
        )
    if not source.clone_path:
        source.clone_path = _make_clone_path(source.id)
        await save_source(source)

    task_id = str(uuid.uuid4())
    asyncio.create_task(_do_sync(source))
    logger.info("Sync initiated for source %s (task %s)", source_id, task_id)
    resp = SourceSyncResponse(
        source_id=source_id,
        task_id=task_id,
        status="started",
        message="Sync started in background. Poll /sources/{id} for status.",
    )
    return JSONResponse(resp.model_dump())


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="share_source",
    error_code_prefix="CODEBASE",
)
@router.post("/sources/{source_id}/share")
async def share_code_source(source_id: str, request: SourceShareRequest):
    """Update access control settings for a code source."""
    source = await get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")
    source.access = request.access
    source.shared_with = request.user_ids
    await save_source(source)
    logger.info("Updated sharing for source %s: %s", source_id, request.access)
    return JSONResponse(source.model_dump())
