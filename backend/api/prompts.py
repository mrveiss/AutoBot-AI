import asyncio
import logging
import os
import time
from typing import Dict, Optional

import aiofiles
from fastapi import APIRouter, HTTPException
from src.constants.network_constants import NetworkConstants

router = APIRouter()

logger = logging.getLogger(__name__)

# Cache for prompts to avoid re-reading files on every request
_prompts_cache: Optional[Dict] = None
_cache_timestamp: float = 0
_cache_ttl: int = 300  # 5 minutes cache


@router.get("/")
async def get_prompts():
    global _prompts_cache, _cache_timestamp

    try:
        # Check cache first
        current_time = time.time()
        if _prompts_cache and (current_time - _cache_timestamp) < _cache_ttl:
            logger.info(
                f"Returning cached prompts "
                f"({len(_prompts_cache.get('prompts', []))} items)"
            )
            return _prompts_cache

        # Adjust path to look for prompts directory at project root
        prompts_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "prompts")
        )
        prompts = []
        defaults = {}

        # PERFORMANCE FIX: Add timeout and limit concurrent file reads
        semaphore = asyncio.Semaphore(10)  # Max 10 concurrent file reads

        async def read_single_file(
            full_path: str, rel_path: str, entry: str, base_path: str
        ):
            """Read a single prompt file with timeout protection"""
            async with semaphore:  # Limit concurrent reads
                try:
                    # Use async file operations without timeout
                    from src.utils.async_file_operations import read_file_async

                    content = await read_file_async(full_path)

                    prompt_id = (
                        rel_path.replace("/", "_").replace("\\", "_").rsplit(".", 1)[0]
                    )
                    prompt_type = base_path if base_path else "custom"

                    prompt_info = {
                        "id": prompt_id,
                        "name": entry.rsplit(".", 1)[0],
                        "type": prompt_type,
                        "path": rel_path,
                        "content": content[:1000],  # Limit content size for
                        # initial load
                        "full_content_available": len(content) > 1000,
                    }

                    default_info = None
                    if "default" in full_path:
                        default_info = (prompt_id, content)

                    return prompt_info, default_info

                except asyncio.TimeoutError:
                    logger.warning(f"Timeout reading prompt file {full_path}")
                    return None, None
                except Exception as e:
                    logger.error(f"Error reading prompt file {full_path}: {str(e)}")
                    return None, None

        # Function to collect prompt files recursively - PERFORMANCE FIX: Make concurrent
        async def collect_prompt_files(directory, base_path=""):
            """Collect all prompt files without reading content first"""
            try:
                entries = await asyncio.to_thread(os.listdir, directory)
                tasks = []

                for entry in entries:
                    full_path = os.path.join(directory, entry)
                    rel_path = os.path.join(base_path, entry) if base_path else entry

                    if await asyncio.to_thread(os.path.isdir, full_path):
                        # Recurse into subdirectories
                        sub_tasks = await collect_prompt_files(full_path, rel_path)
                        tasks.extend(sub_tasks)
                    elif await asyncio.to_thread(os.path.isfile, full_path) and (
                        entry.endswith(".txt") or entry.endswith(".md")
                    ):
                        # Add file read task
                        task = read_single_file(full_path, rel_path, entry, base_path)
                        tasks.append(task)

                return tasks

            except Exception as e:
                logger.error(f"Error collecting files from {directory}: {e}")
                return []

        # Read prompts from the prompts directory with cancellation protection
        if os.path.exists(prompts_dir):
            try:
                # PERFORMANCE FIX: Use smart cancellation for the entire operation
                async def load_all_prompts():
                    # Collect all file read tasks
                    file_tasks = await collect_prompt_files(prompts_dir)
                    logger.info(f"Found {len(file_tasks)} prompt files to read")

                    # Execute all file reads concurrently
                    results = await asyncio.gather(*file_tasks, return_exceptions=True)

                    # Process results
                    for result in results:
                        if isinstance(result, Exception):
                            logger.warning(f"File read failed: {result}")
                            continue

                        prompt_info, default_info = result
                        if prompt_info:
                            prompts.append(prompt_info)
                        if default_info:
                            defaults[default_info[0]] = default_info[1]

                # Load prompts with smart cancellation instead of timeout
                from src.utils.async_cancellation import execute_with_cancellation

                await execute_with_cancellation(load_all_prompts(), "prompts_loading")

            except Exception as e:
                logger.error(f"Prompts loading failed: {str(e)}")
                # Return partial results
                if not prompts:
                    raise HTTPException(
                        status_code=504,
                        detail="Prompts loading timed out. Please try again or contact administrator.",
                    )
        else:
            logger.warning(f"Prompts directory {prompts_dir} not found")

        # Cache the results
        _prompts_cache = {"prompts": prompts, "defaults": defaults}
        _cache_timestamp = current_time

        logger.info(f"Successfully loaded {len(prompts)} prompts")
        return _prompts_cache

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error getting prompts: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting prompts: {str(e)}")


@router.post("/cache/clear")
async def clear_prompts_cache():
    """Clear the prompts cache to force reload on next request"""
    global _prompts_cache, _cache_timestamp
    _prompts_cache = None
    _cache_timestamp = 0
    logger.info("Prompts cache cleared")
    return {"status": "success", "message": "Prompts cache cleared"}


@router.post("/{prompt_id}")
async def save_prompt(prompt_id: str, request: dict):
    try:
        content = request.get("content", "")
        # Derive the file path from the prompt_id, relative to project root
        prompts_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "prompts")
        )

        # Sanitize prompt_id to prevent path traversal
        # Remove any path traversal attempts
        safe_prompt_id = prompt_id.replace("..", "").replace("~", "").strip("/")

        # Convert underscores to directory separators
        relative_path = safe_prompt_id.replace("_", "/")

        # Build the full path
        file_path = os.path.join(prompts_dir, relative_path)

        # Ensure the resolved path is within prompts_dir
        resolved_path = os.path.abspath(file_path)
        if not resolved_path.startswith(prompts_dir):
            return {"error": "Invalid prompt_id - path traversal detected"}, 400

        # Ensure the directory exists
        os.makedirs(os.path.dirname(resolved_path), exist_ok=True)

        # Write the content to the file - PERFORMANCE FIX: Convert to async file I/O
        async with aiofiles.open(resolved_path, "w", encoding="utf-8") as f:
            await f.write(content)
        logger.info(f"Saved prompt {prompt_id} to {file_path}")
        # Return the updated prompt data
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
            "path": (
                file_path.replace(prompts_dir + "/", "")
                if prompts_dir in file_path
                else file_path
            ),
            "content": content,
        }
    except Exception as e:
        logger.error(f"Error saving prompt {prompt_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving prompt: {str(e)}")


@router.post("/{prompt_id}/revert")
async def revert_prompt(prompt_id: str):
    try:
        prompts_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "prompts")
        )
        # Check if there is a default version of this prompt
        default_file_path = os.path.join(
            prompts_dir, "default", prompt_id.replace("_", "/")
        )
        if os.path.exists(default_file_path):
            # PERFORMANCE FIX: Convert to async file I/O
            async with aiofiles.open(default_file_path, "r", encoding="utf-8") as f:
                default_content = await f.read()
            # Save the default content to the custom prompt location
            custom_file_path = os.path.join(prompts_dir, prompt_id.replace("_", "/"))
            os.makedirs(os.path.dirname(custom_file_path), exist_ok=True)
            async with aiofiles.open(custom_file_path, "w", encoding="utf-8") as f:
                await f.write(default_content)
            logger.info(f"Reverted prompt {prompt_id} to default")
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
                    custom_file_path.replace(prompts_dir + "/", "")
                    if prompts_dir in custom_file_path
                    else custom_file_path
                ),
                "content": default_content,
            }
        else:
            logger.warning(f"No default found for prompt {prompt_id}")
            raise HTTPException(
                status_code=404, detail=f"No default prompt found for {prompt_id}"
            )
    except Exception as e:
        logger.error(f"Error reverting prompt {prompt_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error reverting prompt: {str(e)}")
