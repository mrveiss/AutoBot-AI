# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Code source registry endpoints (#1133).

CRUD + sync + share for registered code sources.
Mount point: /api/analytics/codebase/sources (via router.py)
"""

import asyncio
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger

from .. import source_service
from ..source_paths import CODE_SOURCES_BASE, make_clone_path
from ..source_models import (
    CodeSource,
    CodeSourceCreateRequest,
    CodeSourceUpdateRequest,
    SourceShareRequest,
    SourceStatus,
    SourceSyncResponse,
)
from ..source_storage import delete_source, get_source, list_sources, save_source

logger = get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _resolve_token(credential_id: str) -> str | None:
    """Return the decrypted token value for a credential ID, or None."""
    try:
        from api.secrets import secrets_manager

        secret = await asyncio.to_thread(secrets_manager.get_secret, credential_id)
        return secret["value"] if secret else None
    except Exception as exc:
        logger.warning("Failed to resolve credential %s: %s", credential_id, exc)
        return None


def _build_clone_url(repo: str, token: str | None) -> str:
    """Build a GitHub clone URL, injecting token if available."""
    if token:
        return f"https://{token}@github.com/{repo}"
    return f"https://github.com/{repo}"


_GIT_TIMEOUT_SECONDS = 120
_CREDENTIAL_URL_RE = re.compile(r"https?://[^@\s]+@", re.IGNORECASE)


def _sanitize_git_error(message: str) -> str:
    """Strip credential tokens from git error messages before storing (#3095)."""
    return _CREDENTIAL_URL_RE.sub("https://***@", message)


async def _run_git_clone(url: str, dest: str, branch: str) -> str:
    """Clone a repo shallowly. Returns stderr on failure.

    A 120-second timeout prevents the background task from hanging
    indefinitely on large repos or network issues (#3092).
    """
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
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=_GIT_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return f"git clone timed out after {_GIT_TIMEOUT_SECONDS}s"
    if proc.returncode != 0:
        return stderr.decode("utf-8", errors="replace")
    return ""


async def _run_git_pull(clone_path: str) -> str:
    """Pull latest changes in an existing clone. Returns stderr on failure.

    A 120-second timeout prevents the background task from hanging
    indefinitely on network issues (#3092).
    """
    proc = await asyncio.create_subprocess_exec(
        "git",
        "-C",
        clone_path,
        "pull",
        "--ff-only",
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=_GIT_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return f"git pull timed out after {_GIT_TIMEOUT_SECONDS}s"
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
            clone_dir = Path(clone_path)
            if clone_dir.is_dir() and (clone_dir / ".git").is_dir():
                err = await _run_git_pull(clone_path)
            else:
                if clone_dir.is_dir():
                    shutil.rmtree(clone_path, ignore_errors=True)
                clone_dir.mkdir(parents=True, exist_ok=True)
                err = await _run_git_clone(url, clone_path, source.branch)

        if err:
            source.status = SourceStatus.ERROR
            source.error_message = _sanitize_git_error(err)[:500]
        else:
            source.status = SourceStatus.READY
            source.last_synced = datetime.now(tz=timezone.utc).isoformat()
            source.error_message = None
            await _trigger_indexing(source)

    except Exception as exc:
        logger.error("Sync failed for source %s: %s", source.id, exc)
        source.status = SourceStatus.ERROR
        source.error_message = _sanitize_git_error(str(exc))[:500]

    await save_source(source)


def _create_sync_cleanup(task_id: str):
    """Done-callback for sync tasks: remove from _active_tasks, log errors (#1467)."""

    def _cleanup(t: asyncio.Task) -> None:
        from ..scanner import _active_tasks

        _active_tasks.pop(task_id, None)
        if t.cancelled():
            logger.info("Sync task %s was cancelled", task_id)
        elif exc := t.exception():
            logger.error("Sync task %s failed: %s", task_id, exc)
        else:
            logger.info("Sync task %s completed", task_id)

    return _cleanup


async def _trigger_indexing(source: CodeSource) -> None:
    """Queue an indexing job for the source's clone path (#1133).

    Uses _run_indexing_subprocess (#1180) to avoid ChromaDB SIGSEGV
    in the main process, and sets _current_indexing_task_id so
    /index/current reports the running job.
    """
    try:
        from ..scanner import (
            _active_tasks,
            _current_indexing_task_id,
            _index_queue,
            _persist_queue_entry,
            _run_indexing_subprocess,
            _tasks_lock,
        )
        from .indexing import _create_cleanup_callback

        task_id = str(uuid.uuid4())
        async with _tasks_lock:
            if _current_indexing_task_id is None:
                import api.codebase_analytics.scanner as _scanner

                _scanner._current_indexing_task_id = task_id
                task = asyncio.create_task(_run_indexing_subprocess(task_id, source.clone_path, source_id=source.id))
                _active_tasks[task_id] = task
                task.add_done_callback(_create_cleanup_callback(task_id))
            else:
                entry = {
                    "source_id": source.id,
                    "root_path": source.clone_path,
                    "queued_at": datetime.now(tz=timezone.utc).isoformat(),
                    "requested_by": "sync",
                }
                _index_queue.append(entry)
                await _persist_queue_entry(entry)
    except Exception as exc:
        logger.warning("Could not trigger indexing for %s: %s", source.id, exc)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/sources")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_sources",
    error_code_prefix="CODEBASE",
)
async def list_code_sources():
    """List all registered code sources."""
    sources = await list_sources()
    return JSONResponse({"sources": [s.model_dump() for s in sources]})


@router.post("/sources")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_source",
    error_code_prefix="CODEBASE",
)
async def create_code_source(request: CodeSourceCreateRequest):
    """Register a new code source."""
    if request.source_type == "github" and request.repo:
        source = await source_service.create_github_source(
            name=request.name,
            repo=request.repo,
            credential_id=request.credential_id,
            branch=request.branch,
            access=request.access,
            auto_sync=True,
        )
    else:
        source = CodeSource(
            name=request.name,
            source_type=request.source_type,
            repo=request.repo,
            branch=request.branch,
            credential_id=request.credential_id,
            access=request.access,
        )
        if source.source_type == "local" and source.repo:
            source.clone_path = source.repo
        await save_source(source)
        logger.info("Created code source %s (%s)", source.id, source.name)

    return JSONResponse(source.model_dump(), status_code=201)


@router.get("/sources/summary")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="batch_source_summary",
    error_code_prefix="CODEBASE",
)
async def get_all_source_summaries():
    """Return summaries for all sources in one request (#1468).

    Replaces N+1 per-source /summary calls from the landing page.
    Registered before /sources/{source_id} to avoid the literal
    string "summary" being captured by the {source_id} path parameter (#2654, #3107).
    """
    sources = await list_sources()
    results = await asyncio.gather(*[_build_summary(s) for s in sources])
    summaries = {r["source_id"]: r for r in results}
    return JSONResponse({"summaries": summaries})


@router.get("/sources/{source_id}")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_source",
    error_code_prefix="CODEBASE",
)
async def get_code_source(source_id: str):
    """Retrieve a code source by ID."""
    source = await get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")
    return JSONResponse(source.model_dump())


@router.put("/sources/{source_id}")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_source",
    error_code_prefix="CODEBASE",
)
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


@router.delete("/sources/{source_id}")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_source",
    error_code_prefix="CODEBASE",
)
async def delete_code_source(source_id: str):
    """Delete a code source and remove its clone directory if present."""
    source = await get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")
    if source.clone_path and Path(source.clone_path).exists():
        # Only remove clone directories we created (under CODE_SOURCES_BASE)
        clone = Path(source.clone_path).resolve()
        if clone.is_relative_to(CODE_SOURCES_BASE):
            shutil.rmtree(source.clone_path, ignore_errors=True)
    ok = await delete_source(source_id)
    logger.info("Deleted code source %s", source_id)
    return JSONResponse({"success": ok, "source_id": source_id})


@router.post("/sources/{source_id}/sync")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="sync_source",
    error_code_prefix="CODEBASE",
)
async def sync_code_source(source_id: str):
    """Trigger an async clone/pull for a code source."""
    source = await get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")
    if source.source_type == "local":
        # Local sources skip git ops — validate path and trigger indexing
        if not source.clone_path or not Path(source.clone_path).is_dir():
            raise HTTPException(
                status_code=400,
                detail=f"Local path not found: {source.clone_path}",
            )
        source.status = SourceStatus.READY
        source.last_synced = datetime.now(tz=timezone.utc).isoformat()
        await save_source(source)
        await _trigger_indexing(source)
        resp = SourceSyncResponse(
            source_id=source_id,
            task_id="local",
            status="started",
            message="Indexing triggered for local source.",
        )
        return JSONResponse(resp.model_dump())

    if not source.clone_path:
        source.clone_path = make_clone_path(source.id)
        await save_source(source)

    from ..scanner import _active_tasks

    task_id = str(uuid.uuid4())
    task = asyncio.create_task(_do_sync(source))
    _active_tasks[task_id] = task
    task.add_done_callback(_create_sync_cleanup(task_id))
    logger.info("Sync initiated for source %s (task %s)", source_id, task_id)
    resp = SourceSyncResponse(
        source_id=source_id,
        task_id=task_id,
        status="started",
        message="Sync started in background. Poll /sources/{id} for status.",
    )
    return JSONResponse(resp.model_dump())


@router.post("/sources/{source_id}/share")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="share_source",
    error_code_prefix="CODEBASE",
)
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


async def _get_last_indexed(source_id: str) -> str | None:
    """Read last_indexed timestamp from ChromaDB stats metadata.

    Helper for get_source_summary (#1458).
    Issue #1716: Reads per-source stats doc first, falls back to global.
    """
    try:
        from ..storage import get_code_collection_async

        collection = await get_code_collection_async()
        if collection:
            # Try per-source stats first (#1716), fall back to global
            stats_id = f"codebase_stats_{source_id}"
            results = await collection.get(
                ids=[stats_id],
                include=["metadatas"],
            )
            if not results or not results.get("metadatas"):
                results = await collection.get(
                    ids=["codebase_stats"],
                    include=["metadatas"],
                )
            if results and results.get("metadatas"):
                return results["metadatas"][0].get("last_indexed")
    except Exception as exc:
        logger.warning(
            "Could not read last_indexed for %s: %s",
            source_id,
            exc,
        )
    return None


async def _get_last_commit(clone_path: str, repo: str | None, is_local: bool = False) -> dict | None:
    """Read latest git commit info from a clone directory.

    Helper for get_source_summary (#1458).
    Issue #1756: Allow local source paths outside CODE_SOURCES_BASE.
    """
    clone = Path(clone_path)
    if not clone.is_dir():
        return None
    # Only enforce base-dir check for managed clones, not local sources
    if not is_local and not clone.resolve().is_relative_to(CODE_SOURCES_BASE):
        logger.warning("Clone path %s outside base directory", clone_path)
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            str(clone),
            "log",
            "-1",
            "--format=%H%n%h%n%s%n%aI",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0 or not stdout:
            return None
        lines = stdout.decode("utf-8").strip().split("\n")
        if len(lines) < 4:
            return None
        url = None
        if repo:
            url = f"https://github.com/{repo}/commit/{lines[0]}"
        return {
            "hash": lines[0],
            "short_hash": lines[1],
            "message": lines[2],
            "timestamp": lines[3],
            "url": url,
        }
    except Exception as exc:
        logger.warning(
            "Could not read last commit for %s: %s",
            clone_path,
            exc,
        )
        return None


async def _build_summary(source: CodeSource) -> dict:
    """Build summary dict for a single source (#1468)."""
    last_indexed = None
    last_commit = None
    if source.clone_path:
        last_indexed = await _get_last_indexed(source.id)
        last_commit = await _get_last_commit(
            source.clone_path,
            source.repo,
            is_local=(source.source_type == "local"),
        )
    return {
        "source_id": source.id,
        "last_indexed": last_indexed,
        "last_commit": last_commit,
    }


@router.get("/sources/{source_id}/summary")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="source_summary",
    error_code_prefix="CODEBASE",
)
async def get_source_summary(source_id: str):
    """Return summary info for a source (#1458).

    Provides last_indexed and last_commit for landing page cards.
    """
    source = await get_source(source_id)
    if source is None:
        raise HTTPException(
            status_code=404,
            detail=f"Source {source_id} not found",
        )

    last_indexed = None
    last_commit = None
    if source.clone_path:
        last_indexed = await _get_last_indexed(source_id)
        last_commit = await _get_last_commit(
            source.clone_path,
            source.repo,
            is_local=(source.source_type == "local"),
        )

    return JSONResponse(
        {
            "source_id": source_id,
            "last_indexed": last_indexed,
            "last_commit": last_commit,
        }
    )
