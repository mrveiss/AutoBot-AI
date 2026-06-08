# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Sandbox File Management API

Provides file management endpoints scoped to the sandbox root directory.
Mirrors api/files.py but rooted at sandbox_files_root instead of file_manager_root.

GH#7409
"""

import logging
import shutil
import urllib.parse
from pathlib import Path

import aiofiles
from fastapi import APIRouter, Form, HTTPException, Request

from api.files import ALLOWED_EXTENSIONS, INVALID_PATH_CHARACTERS, get_file_info
from api.schemas_code import (
    FileSandboxCreateDirResponse,
    FileSandboxDeleteResponse,
    FileSandboxPreviewResponse,
    FileSandboxRenameResponse,
    FileSandboxStatsResponse,
    FileSandboxTreeResponse,
    FileSandboxViewResponse,
)
from auth_middleware import get_auth_middleware
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.security.path_validator import validate_relative_path
from constants.error_constants import ERR_DIRECTORY_NOT_FOUND, ERR_FILE_NOT_FOUND
from utils.io_executor import run_in_file_executor
from utils.path_validation import is_invalid_name
from utils.paths_manager import get_data_path

router = APIRouter()
logger = logging.getLogger(__name__)

SANDBOX_FILES_ROOT = get_data_path("sandbox_files_root").resolve()
SANDBOX_FILES_ROOT.mkdir(parents=True, exist_ok=True)


def _check_permission(request: Request, permission: str) -> dict:
    has_permission, user_data = get_auth_middleware().check_file_permissions(request, permission)
    if not has_permission:
        raise HTTPException(
            status_code=403,
            detail=f"Insufficient permissions for file {permission} operations",
        )
    request.state.user = user_data
    return user_data


def _validate_path(path: str) -> Path:
    """Validate and resolve a path within the sandbox root directory."""
    if not path:
        return SANDBOX_FILES_ROOT

    clean_path = path.strip("/")

    if (
        ".." in clean_path
        or clean_path.startswith("/")
        or "~" in clean_path
        or any(char in clean_path for char in INVALID_PATH_CHARACTERS)
    ):
        raise HTTPException(status_code=400, detail="Invalid path: path traversal not allowed")

    decoded_path = urllib.parse.unquote(clean_path)
    if ".." in decoded_path or decoded_path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid path: encoded traversal not allowed")

    try:
        return validate_relative_path(clean_path, SANDBOX_FILES_ROOT)
    except ValueError:
        raise HTTPException(status_code=400, detail="Path outside sandbox not allowed")


@router.get("/view/{file_path:path}", response_model=FileSandboxViewResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="sandbox_view_file",
    error_code_prefix="SANDBOX_FILES",
)
async def view_file(request: Request, file_path: str):
    """View file content (for text files) or get file metadata."""
    _check_permission(request, "view")
    target_file = _validate_path(file_path)

    if not await run_in_file_executor(target_file.exists):
        raise HTTPException(status_code=404, detail=ERR_FILE_NOT_FOUND)
    if not await run_in_file_executor(target_file.is_file):
        raise HTTPException(status_code=400, detail="Path is not a file")

    relative_path = str(target_file.relative_to(SANDBOX_FILES_ROOT))
    file_info = await run_in_file_executor(get_file_info, target_file, relative_path)

    content: str | None = None
    if file_info.mime_type and file_info.mime_type.startswith("text/"):
        try:
            async with aiofiles.open(target_file, "r", encoding="utf-8") as f:
                content = await f.read()
        except OSError as e:
            logger.error("Failed to read file %s: %s", target_file, e)
            raise HTTPException(status_code=500, detail="Internal server error")
        except UnicodeDecodeError:
            pass

    return {"file_info": file_info, "content": content, "is_text": content is not None}


@router.post("/rename", response_model=FileSandboxRenameResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="sandbox_rename_file",
    error_code_prefix="SANDBOX_FILES",
)
async def rename_file_or_directory(request: Request, path: str = Form(...), new_name: str = Form(...)):
    """Rename a file or directory within the sandbox."""
    _check_permission(request, "upload")

    if is_invalid_name(new_name):
        raise HTTPException(status_code=400, detail="Invalid file/directory name")

    source_path = _validate_path(path)

    if not await run_in_file_executor(source_path.exists):
        raise HTTPException(status_code=404, detail="File or directory not found")

    target_path = source_path.parent / new_name

    if await run_in_file_executor(target_path.exists):
        raise HTTPException(status_code=409, detail="A file or directory with that name already exists")

    await run_in_file_executor(source_path.rename, target_path)

    relative_path = str(target_path.relative_to(SANDBOX_FILES_ROOT))
    item_info = await run_in_file_executor(get_file_info, target_path, relative_path)

    return {"message": f"Successfully renamed to '{new_name}'", "item_info": item_info}


@router.get("/preview", response_model=FileSandboxPreviewResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="sandbox_preview_file",
    error_code_prefix="SANDBOX_FILES",
)
async def preview_file(request: Request, path: str):
    """Get file preview with content and metadata."""
    _check_permission(request, "view")
    target_file = _validate_path(path)

    if not await run_in_file_executor(target_file.exists):
        raise HTTPException(status_code=404, detail=ERR_FILE_NOT_FOUND)
    if not await run_in_file_executor(target_file.is_file):
        raise HTTPException(status_code=400, detail="Path is not a file")

    relative_path = str(target_file.relative_to(SANDBOX_FILES_ROOT))
    file_info = await run_in_file_executor(get_file_info, target_file, relative_path)

    mime_type = file_info.mime_type
    if not mime_type:
        file_type = "binary"
    elif mime_type.startswith("text/"):
        file_type = "text"
    elif mime_type.startswith("image/"):
        file_type = "image"
    elif mime_type == "application/pdf":
        file_type = "pdf"
    else:
        file_type = "binary"

    content: str | None = None
    if file_type == "text":
        try:
            async with aiofiles.open(target_file, "r", encoding="utf-8") as f:
                content = await f.read()
        except OSError as e:
            logger.error("Failed to read file %s: %s", target_file, e)
            raise HTTPException(status_code=500, detail="Internal server error")
        except UnicodeDecodeError:
            file_type = "binary"

    return {
        "type": file_type,
        "url": f"/api/sandbox/files/view/{path}",
        "content": content,
        "mime_type": mime_type,
        "size": file_info.size or 0,
        "name": file_info.name,
    }


@router.delete("/delete", response_model=FileSandboxDeleteResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="sandbox_delete_file",
    error_code_prefix="SANDBOX_FILES",
)
async def delete_file(request: Request, path: str):
    """Delete a file or directory within the sandbox."""
    _check_permission(request, "delete")
    target_path = _validate_path(path)

    if not await run_in_file_executor(target_path.exists):
        raise HTTPException(status_code=404, detail="File or directory not found")

    is_file = await run_in_file_executor(target_path.is_file)
    if is_file:
        await run_in_file_executor(target_path.unlink)
        return {"message": f"File '{path}' deleted successfully"}

    await run_in_file_executor(shutil.rmtree, target_path)
    return {"message": f"Directory '{path}' deleted successfully"}


@router.post("/create_directory", response_model=FileSandboxCreateDirResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="sandbox_create_directory",
    error_code_prefix="SANDBOX_FILES",
)
async def create_directory(request: Request, path: str = Form(...), name: str = Form(...)):
    """Create a new directory within the sandbox."""
    _check_permission(request, "upload")

    if is_invalid_name(name):
        raise HTTPException(status_code=400, detail="Invalid directory name")

    parent_dir = _validate_path(path)
    new_dir = parent_dir / name

    if await run_in_file_executor(new_dir.exists):
        raise HTTPException(status_code=409, detail="Directory already exists")

    await run_in_file_executor(lambda: new_dir.mkdir(parents=True, exist_ok=False))

    relative_path = str(new_dir.relative_to(SANDBOX_FILES_ROOT))
    dir_info = await run_in_file_executor(get_file_info, new_dir, relative_path)

    return {"message": f"Directory '{name}' created successfully", "directory_info": dir_info}


@router.get("/tree", response_model=FileSandboxTreeResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="sandbox_get_directory_tree",
    error_code_prefix="SANDBOX_FILES",
)
async def get_directory_tree(request: Request, path: str = ""):
    """Get directory tree structure."""
    _check_permission(request, "view")
    target_path = _validate_path(path)

    if not await run_in_file_executor(target_path.exists):
        raise HTTPException(status_code=404, detail=ERR_DIRECTORY_NOT_FOUND)
    if not await run_in_file_executor(target_path.is_dir):
        raise HTTPException(status_code=400, detail="Path is not a directory")

    def build_tree(directory: Path) -> list:
        try:
            items = []
            for item in sorted(directory.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                try:
                    rel = str(item.relative_to(SANDBOX_FILES_ROOT))
                    entry: dict = {
                        "name": item.name,
                        "path": rel,
                        "type": "directory" if item.is_dir() else "file",
                    }
                    if item.is_file():
                        entry["size"] = item.stat().st_size
                        entry["extension"] = item.suffix.lower() if item.suffix else None
                    else:
                        entry["children"] = build_tree(item)
                    items.append(entry)
                except (OSError, PermissionError) as e:
                    logger.warning("Skipping inaccessible item %s: %s", item, e)
            return items
        except Exception as e:
            logger.error("Error building tree for %s: %s", directory, e)
            return []

    tree_data = await run_in_file_executor(build_tree, target_path)
    return {"path": path, "tree": tree_data}


@router.get("/stats", response_model=FileSandboxStatsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="sandbox_get_file_stats",
    error_code_prefix="SANDBOX_FILES",
)
async def get_file_stats(request: Request):
    """Get file system statistics for the sandbox root."""
    _check_permission(request, "view")

    def _collect_stats_sync() -> tuple:
        total_files = 0
        total_directories = 0
        total_size = 0
        for item in SANDBOX_FILES_ROOT.rglob("*"):
            if item.is_file():
                total_files += 1
                total_size += item.stat().st_size
            elif item.is_dir():
                total_directories += 1
        return total_files, total_directories, total_size

    total_files, total_directories, total_size = await run_in_file_executor(_collect_stats_sync)

    return {
        "sandbox_root": str(SANDBOX_FILES_ROOT),
        "total_files": total_files,
        "total_directories": total_directories,
        "total_size": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "max_file_size_mb": 50,
        "allowed_extensions": sorted(list(ALLOWED_EXTENSIONS)),
    }
