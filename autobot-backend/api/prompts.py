# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Prompt template management endpoints.

Provides CRUD for system prompt templates stored on disk, including
async file I/O and per-request timing instrumentation.
"""

import asyncio
import os
import time
from typing import Dict

import aiofiles
from fastapi import APIRouter, Depends, HTTPException

from api.schemas_workflows import (
    PromptRevertResponse,
    PromptSaveResponse,
    PromptsCacheClearResponse,
    PromptsListResponse,
)
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.security.path_validator import validate_relative_path
from constants.ttl_constants import TTL_5_MINUTES

router = APIRouter()


def _validate_prompt_id(prompt_id: str) -> str:
    """Ensure prompt_id has no path traversal (#1733)."""
    if ".." in prompt_id or prompt_id.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid prompt ID")
    return prompt_id


logger = get_logger(__name__)

# Cache for prompts to avoid re-reading files on every request
_prompts_cache: Dict | None = None
_cache_timestamp: float = 0
_cache_ttl: int = TTL_5_MINUTES

# Lock for thread-safe cache access
_cache_lock = asyncio.Lock()

# Issue #514: Per-file locking to prevent concurrent write corruption
_prompt_file_locks: Dict[str, asyncio.Lock] = {}
_prompt_locks_lock = asyncio.Lock()


async def _get_prompt_file_lock(filepath: str) -> asyncio.Lock:
    """
    Get or create a lock for a specific prompt file path (Issue #514).

    Uses per-file locking to allow concurrent writes to different prompts
    while preventing corruption from concurrent writes to the same file.

    Args:
        filepath: Absolute path to the prompt file

    Returns:
        asyncio.Lock for the specified file
    """
    async with _prompt_locks_lock:
        if filepath not in _prompt_file_locks:
            _prompt_file_locks[filepath] = asyncio.Lock()
        return _prompt_file_locks[filepath]


async def _read_prompt_file(
    full_path: str,
    rel_path: str,
    entry: str,
    base_path: str,
    semaphore: asyncio.Semaphore,
) -> tuple:
    """Read a single prompt file with semaphore-limited concurrency (Issue #315: extracted).

    Returns:
        Tuple of (prompt_info, default_info) or (None, None) on error
    """
    async with semaphore:
        try:
            from utils.async_file_operations import read_file_async

            content = await read_file_async(full_path)

            prompt_id = rel_path.replace("/", "_").replace("\\", "_").rsplit(".", 1)[0]
            prompt_type = base_path if base_path else "custom"

            prompt_info = {
                "id": prompt_id,
                "name": entry.rsplit(".", 1)[0],
                "type": prompt_type,
                "path": rel_path,
                "content": content[:1000],
                "full_content_available": len(content) > 1000,
            }

            default_info = None
            if "default" in full_path:
                default_info = (prompt_id, content)

            return prompt_info, default_info

        except asyncio.TimeoutError:
            logger.warning("Timeout reading prompt file %s", full_path)
            return None, None
        except Exception as e:
            logger.error("Error reading prompt file %s: %s", full_path, str(e))
            return None, None


def _is_prompt_file(entry: str) -> bool:
    """Check if entry is a prompt file (Issue #315: extracted)."""
    return entry.endswith(".txt") or entry.endswith(".md")


def _process_prompt_results(results: list, prompts: list, defaults: dict) -> None:
    """Process gathered prompt results into prompts/defaults (Issue #315: extracted)."""
    for result in results:
        if isinstance(result, Exception):
            logger.warning("File read failed: %s", result)
            continue
        if result is None:
            continue

        prompt_info, default_info = result
        if prompt_info:
            prompts.append(prompt_info)
        if default_info:
            defaults[default_info[0]] = default_info[1]


async def _load_all_prompts(prompts_dir: str, semaphore: asyncio.Semaphore, prompts: list, defaults: dict) -> None:
    """Load all prompt files from directory concurrently (Issue #315: extracted).

    Args:
        prompts_dir: Directory containing prompt files
        semaphore: Semaphore for limiting concurrent file reads
        prompts: List to append prompt info to (mutated in place)
        defaults: Dict to add default prompts to (mutated in place)
    """
    # Collect file read tasks using module-level helper
    file_tasks = await _collect_prompt_files(prompts_dir, "", semaphore)
    logger.info("Found %s prompt files to read", len(file_tasks))

    # Execute all file reads concurrently
    results = await asyncio.gather(*file_tasks, return_exceptions=True)

    # Process results using module-level helper
    _process_prompt_results(results, prompts, defaults)


async def _load_prompts_with_cancellation(
    prompts_dir: str, semaphore: asyncio.Semaphore, prompts: list, defaults: dict
) -> None:
    """Load prompts with smart cancellation handling (Issue #315: extracted).

    Args:
        prompts_dir: Directory containing prompt files
        semaphore: Semaphore for limiting concurrent file reads
        prompts: List to append prompt info to (mutated in place)
        defaults: Dict to add default prompts to (mutated in place)

    Raises:
        HTTPException: If loading times out and no prompts were loaded
    """
    from utils.async_cancellation import execute_with_cancellation

    try:
        await execute_with_cancellation(
            _load_all_prompts(prompts_dir, semaphore, prompts, defaults),
            "prompts_loading",
        )
    except Exception as e:
        logger.error("Prompts loading failed: %s", str(e))
        # Return partial results if we have any
        if not prompts:
            raise HTTPException(
                status_code=504,
                detail=("Prompts loading timed out. Please try again or " "contact administrator."),
            )


async def _collect_prompt_files(directory: str, base_path: str, semaphore: asyncio.Semaphore) -> list:
    """Collect prompt file read tasks recursively (Issue #315: extracted).

    Returns:
        List of coroutine tasks to read prompt files
    """
    try:
        entries = await asyncio.to_thread(os.listdir, directory)
        tasks = []

        for entry in entries:
            full_path = os.path.join(directory, entry)
            rel_path = os.path.join(base_path, entry) if base_path else entry

            # Handle directories - recurse
            if await asyncio.to_thread(os.path.isdir, full_path):
                sub_tasks = await _collect_prompt_files(full_path, rel_path, semaphore)
                tasks.extend(sub_tasks)
                continue

            # Skip non-files
            if not await asyncio.to_thread(os.path.isfile, full_path):
                continue

            # Skip non-prompt files
            if not _is_prompt_file(entry):
                continue

            # Add prompt file read task
            task = _read_prompt_file(full_path, rel_path, entry, base_path, semaphore)
            tasks.append(task)

        return tasks

    except Exception as e:
        logger.error("Error collecting files from %s: %s", directory, e)
        return []


@router.get("/", response_model=PromptsListResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_prompts",
    error_code_prefix="PROMPTS",
)
async def get_prompts(admin_check: bool = Depends(check_admin_permission)):
    """Get all prompts from filesystem with caching.

    Issue #744: Requires admin authentication.
    """
    global _prompts_cache, _cache_timestamp

    try:
        # Check cache first (thread-safe)
        current_time = time.time()
        async with _cache_lock:
            if _prompts_cache and (current_time - _cache_timestamp) < _cache_ttl:
                logger.info(f"Returning cached prompts " f"({len(_prompts_cache.get('prompts', []))} items)")
                return _prompts_cache

        # Adjust path to look for prompts directory at project root
        # Issue #358 - avoid blocking
        prompts_dir = await asyncio.to_thread(
            os.path.abspath,
            os.path.join(os.path.dirname(__file__), "..", "resources", "prompts"),
        )
        prompts = []
        defaults = {}

        # PERFORMANCE FIX: Add timeout and limit concurrent file reads
        semaphore = asyncio.Semaphore(10)  # Max 10 concurrent file reads

        # Read prompts from the prompts directory with cancellation protection
        # (Issue #315: inner functions moved to module level to reduce nesting)
        # Issue #358 - avoid blocking
        if not await asyncio.to_thread(os.path.exists, prompts_dir):
            logger.warning("Prompts directory %s not found", prompts_dir)
        else:
            await _load_prompts_with_cancellation(prompts_dir, semaphore, prompts, defaults)

        # Cache the results (thread-safe)
        async with _cache_lock:
            _prompts_cache = {"prompts": prompts, "defaults": defaults}
            _cache_timestamp = current_time

        logger.info("Successfully loaded %s prompts", len(prompts))
        return _prompts_cache

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error("Error getting prompts: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Error getting prompts")


@router.post("/cache/clear", response_model=PromptsCacheClearResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_prompts_cache",
    error_code_prefix="PROMPTS",
)
async def clear_prompts_cache(admin_check: bool = Depends(check_admin_permission)):
    """Clear the prompts cache to force reload on next request.

    Issue #744: Requires admin authentication.
    """
    global _prompts_cache, _cache_timestamp
    async with _cache_lock:
        _prompts_cache = None
        _cache_timestamp = 0
    logger.info("Prompts cache cleared")
    return {"status": "success", "message": "Prompts cache cleared"}


def _build_prompt_save_response(prompt_id: str, file_path: str, content: str, prompts_dir: str) -> dict:
    """Helper for save_prompt. Ref: #1088."""
    prompt_name = os.path.basename(file_path).rsplit(".", 1)[0]
    prompt_type = (
        os.path.dirname(file_path).replace(prompts_dir + "/", "")
        if prompts_dir in file_path
        else os.path.dirname(file_path)
    )
    return {
        "id": prompt_id,
        "name": prompt_name,
        "type": prompt_type if prompt_type else "custom",
        "path": (file_path.replace(prompts_dir + "/", "") if prompts_dir in file_path else file_path),
        "content": content,
    }


@router.post("/{prompt_id}", response_model=PromptSaveResponse)
@router.put("/{prompt_id}", response_model=PromptSaveResponse)  # Issue #570: Support PUT for frontend compatibility
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="save_prompt",
    error_code_prefix="PROMPTS",
)
async def save_prompt(prompt_id: str, request: dict, admin_check: bool = Depends(check_admin_permission)):
    """Save or update a prompt file by ID.

    Issue #744: Requires admin authentication.
    """
    try:
        content = request.get("content", "")
        # Derive the file path from the prompt_id, relative to project root
        # Issue #358 - avoid blocking
        prompts_dir = await asyncio.to_thread(
            os.path.abspath,
            os.path.join(os.path.dirname(__file__), "..", "resources", "prompts"),
        )

        # Sanitize prompt_id to prevent path traversal (#1721)
        safe_prompt_id = prompt_id.replace("..", "").replace("~", "").strip("/")
        relative_path = safe_prompt_id.replace("_", "/")

        try:
            resolved_path = str(validate_relative_path(relative_path, prompts_dir))
        except ValueError:
            return {"error": "Invalid prompt_id - path traversal detected"}, 400

        # Ensure the directory exists
        # Issue #358 - avoid blocking
        await asyncio.to_thread(os.makedirs, os.path.dirname(resolved_path), exist_ok=True)

        # Write the content to the file - PERFORMANCE FIX: Convert to async file I/O
        # Issue #514: Use per-file locking to prevent concurrent write corruption
        file_lock = await _get_prompt_file_lock(resolved_path)
        async with file_lock:
            async with aiofiles.open(resolved_path, "w", encoding="utf-8") as f:  # codeql[py/path-injection]
                await f.write(content)
        logger.info("Saved prompt %s to %s", prompt_id, resolved_path)
        return _build_prompt_save_response(prompt_id, resolved_path, content, prompts_dir)
    except OSError as e:
        logger.error("Failed to write prompt file %s: %s", prompt_id, e)
        raise HTTPException(status_code=500, detail="Failed to save prompt file")
    except Exception as e:
        logger.error("Error saving prompt %s: %s", prompt_id, str(e))
        raise HTTPException(status_code=500, detail="Error saving prompt")


async def _write_prompt_from_default(prompt_id: str, default_file_path: str, prompts_dir: str) -> dict:
    """Read the default prompt file and overwrite the custom location. Ref: #2735.

    Uses per-file locking (#514) to prevent concurrent write corruption.
    Returns the response dict for revert_prompt on success.
    Raises HTTPException(404) if the default file is absent.
    """
    if not await asyncio.to_thread(os.path.exists, default_file_path):
        logger.warning("No default found for prompt %s", prompt_id)
        raise HTTPException(status_code=404, detail=f"No default prompt found for {prompt_id}")

    async with aiofiles.open(default_file_path, "r", encoding="utf-8") as f:  # codeql[py/path-injection]
        default_content = await f.read()

    custom_file_path = str(validate_relative_path(prompt_id.replace("_", "/"), prompts_dir))
    await asyncio.to_thread(os.makedirs, os.path.dirname(custom_file_path), exist_ok=True)

    # Issue #514: per-file locking to prevent concurrent write corruption
    file_lock = await _get_prompt_file_lock(custom_file_path)
    async with file_lock:
        async with aiofiles.open(custom_file_path, "w", encoding="utf-8") as f:  # codeql[py/path-injection]
            await f.write(default_content)

    logger.info("Reverted prompt %s to default", prompt_id)
    prompt_name = os.path.basename(custom_file_path).rsplit(".", 1)[0]
    prompt_type = (
        os.path.dirname(custom_file_path).replace(prompts_dir + "/", "")
        if prompts_dir in custom_file_path
        else os.path.dirname(custom_file_path)
    )
    return {
        "id": prompt_id,
        "name": prompt_name,
        "type": prompt_type if prompt_type else "custom",
        "path": (
            custom_file_path.replace(prompts_dir + "/", "") if prompts_dir in custom_file_path else custom_file_path
        ),
        "content": default_content,
    }


@router.post("/{prompt_id}/revert", response_model=PromptRevertResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="revert_prompt",
    error_code_prefix="PROMPTS",
)
async def revert_prompt(prompt_id: str, admin_check: bool = Depends(check_admin_permission)):
    """Revert a prompt to its default version.

    Issue #744: Requires admin authentication.
    """
    try:
        # Issue #358 - avoid blocking
        prompts_dir = await asyncio.to_thread(
            os.path.abspath,
            os.path.join(os.path.dirname(__file__), "..", "resources", "prompts"),
        )
        # Check if there is a default version of this prompt (#1721)
        default_file_path = str(
            validate_relative_path(
                os.path.join("default", prompt_id.replace("_", "/")),
                prompts_dir,
            )
        )
        return await _write_prompt_from_default(prompt_id, default_file_path, prompts_dir)
    except HTTPException:
        # Re-raise HTTP exceptions (e.g. 404 from _write_prompt_from_default) — #2745
        raise
    except OSError as e:
        logger.error("Failed to read/write prompt file during revert %s: %s", prompt_id, e)
        raise HTTPException(status_code=500, detail="Failed to access prompt file")
    except Exception as e:
        logger.error("Error reverting prompt %s: %s", prompt_id, str(e))
        raise HTTPException(status_code=500, detail="Error reverting prompt")
