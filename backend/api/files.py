# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Secure File Management API

This module provides secure file management endpoints with proper sandboxing,
path traversal protection, and authentication/authorization.

Issue #718: Uses dedicated thread pool for file I/O to prevent blocking
when the main asyncio thread pool is saturated by indexing operations.
"""

import asyncio
import logging
import mimetypes
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import aiofiles
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer
from pydantic import BaseModel, field_validator

from backend.utils.paths_manager import ensure_data_directory, get_data_path
from backend.utils.io_executor import run_in_file_executor
from src.auth_middleware import auth_middleware
from src.security_layer import SecurityLayer
from src.utils.error_boundaries import ErrorCategory, with_error_handling
from src.utils.path_validation import is_invalid_name

router = APIRouter()
logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)

# Issue #380: Module-level tuple for dangerous content patterns in uploads
_DANGEROUS_CONTENT_PATTERNS = (
    "<script",
    "</script>",
    "javascript:",
    "vbscript:",
    "onload=",
    "onerror=",
    "onclick=",
    "eval(",
    "document.write",
    "innerHTML",
    "<?php",
    "<%",
    "<jsp:",
    "exec(",
    "system(",
    "shell_exec(",
)

# Configure sandboxed directory for file operations using centralized paths

# Ensure data directory exists
ensure_data_directory()

# Get sandboxed root using centralized path management
# CRITICAL: Resolve to absolute path to prevent issues when CWD changes
SANDBOXED_ROOT = get_data_path("file_manager_root").resolve()
SANDBOXED_ROOT.mkdir(parents=True, exist_ok=True)

# Maximum file size (50MB)
MAX_FILE_SIZE = 50 * 1024 * 1024

# Allowed file extensions for security
ALLOWED_EXTENSIONS = {
    # Text and data formats
    ".txt",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".xml",
    ".csv",
    ".log",
    ".cfg",
    ".ini",
    ".con",
    # Code files
    ".py",
    ".js",
    ".ts",
    ".sh",
    ".bat",
    ".sql",
    # Web files
    ".html",
    ".css",
    # Office document formats (Microsoft)
    ".pdf",
    ".doc",
    ".docx",
    ".xlsx",
    ".ppt",
    ".pptx",
    # Office document formats (OpenDocument/LibreOffice)
    ".odt",  # OpenDocument Text (Writer)
    ".ods",  # OpenDocument Spreadsheet (Calc)
    ".odp",  # OpenDocument Presentation (Impress)
    ".odg",  # OpenDocument Graphics (Draw)
    # Image formats
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".pd",
    ".gi",
}

# Performance optimization: O(1) lookup for invalid path characters (Issue #326)
INVALID_PATH_CHARACTERS = {"<", ">", ":", '"', "|", "?", "*"}

# Issue #380: Module-level frozenset for dangerous filename characters
_DANGEROUS_FILENAME_CHARS = frozenset({"<", ">", '"', "|", "?", "*", "\0", "\r", "\n"})

# Issue #398: Module-level sets for is_safe_file validation
_DANGEROUS_FILENAMES = frozenset({
    ".htaccess", ".env", "passwd", "shadow", "config",
    "web.config", "autoexec.bat", "boot.ini", "hosts",
    "httpd.conf", "nginx.conf",
})

_DANGEROUS_EXTENSIONS = frozenset({
    ".exe", ".bat", ".cmd", ".com", ".scr", ".pif", ".vbs",
    ".js", ".jar", ".app", ".deb", ".rpm", ".dmg", ".pkg", ".msi",
})


class FileInfo(BaseModel):
    """File information model"""

    name: str
    path: str
    is_directory: bool
    size: Optional[int] = None
    mime_type: Optional[str] = None
    last_modified: datetime
    permissions: str
    extension: Optional[str] = None


class DirectoryListing(BaseModel):
    """Directory listing response model"""

    current_path: str
    parent_path: Optional[str] = None
    files: List[FileInfo]
    total_files: int
    total_directories: int
    total_size: int


class FileUploadResponse(BaseModel):
    """File upload response model"""

    success: bool
    message: str
    file_info: Optional[FileInfo] = None
    upload_id: Optional[str] = None


class FileOperation(BaseModel):
    """File operation request model"""

    path: str

    @field_validator("path")
    @classmethod
    def validate_path(cls, v):
        """Validate path to prevent directory traversal attacks."""
        if not v or ".." in v or v.startswith("/"):
            raise ValueError("Invalid path")
        return v


def get_security_layer(request: Request) -> SecurityLayer:
    """Get security layer from app state"""
    return request.app.state.security_layer


# Path validation imported from src.utils.path_validation (Issue #328 - shared utility)


def validate_and_resolve_path(path: str) -> Path:
    """
    Validate and resolve a path within the sandboxed directory.
    Prevents path traversal attacks with multiple security layers.
    """
    if not path:
        return SANDBOXED_ROOT

    # Remove leading/trailing slashes and normalize
    clean_path = path.strip("/")

    # Enhanced path traversal checks
    if (
        ".." in clean_path
        or clean_path.startswith("/")
        or "~" in clean_path
        or any(char in clean_path for char in INVALID_PATH_CHARACTERS)
    ):
        raise HTTPException(
            status_code=400, detail="Invalid path: path traversal not allowed"
        )

    # URL decode to catch encoded traversal attempts
    import urllib.parse

    decoded_path = urllib.parse.unquote(clean_path)
    if ".." in decoded_path or decoded_path.startswith("/"):
        raise HTTPException(
            status_code=400, detail="Invalid path: encoded traversal not allowed"
        )

    # Resolve the full path within sandbox
    full_path = SANDBOXED_ROOT / clean_path

    # Use realpath for canonical path resolution (prevents symlink attacks)
    try:
        canonical_full = full_path.resolve(strict=False)
        canonical_sandbox = SANDBOXED_ROOT.resolve()
        canonical_full.relative_to(canonical_sandbox)
    except ValueError:
        raise HTTPException(status_code=400, detail="Path outside sandbox not allowed")

    # Return the canonical (absolute) path to prevent CWD-related issues
    return canonical_full


def get_file_info(file_path: Path, relative_path: str) -> FileInfo:
    """Get file information for a given path"""
    stat = file_path.stat()

    # Get MIME type
    mime_type = None
    if file_path.is_file():
        mime_type, _ = mimetypes.guess_type(str(file_path))

    return FileInfo(
        name=file_path.name,
        path=relative_path,
        is_directory=file_path.is_dir(),
        size=stat.st_size if file_path.is_file() else None,
        mime_type=mime_type,
        last_modified=datetime.fromtimestamp(stat.st_mtime),
        permissions=oct(stat.st_mode)[-3:],
        extension=file_path.suffix.lower() if file_path.suffix else None,
    )


def is_safe_file(filename: str) -> bool:
    """
    Check if file type is allowed and filename is safe.

    Issue #398: Refactored to use module-level constants.
    """
    if not filename:
        return False

    # Check for dangerous characters (Issue #380: module-level constant)
    if any(char in filename for char in _DANGEROUS_FILENAME_CHARS):
        return False

    if len(filename) > 255:
        return False

    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        return False

    # Issue #398: Use module-level sets
    if filename.lower() in _DANGEROUS_FILENAMES:
        return False

    if extension in _DANGEROUS_EXTENSIONS and extension not in ALLOWED_EXTENSIONS:
        return False

    # Prevent null bytes and control characters
    if "\0" in filename or any(ord(c) < 32 for c in filename):
        return False

    return True


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_files",
    error_code_prefix="FILES",
)
@router.get("/list", response_model=DirectoryListing)
async def list_files(request: Request, path: str = ""):
    """
    List files in the specified directory within the sandbox.

    Args:
        path: Relative path within the sandbox (optional, defaults to root)
    """
    # SECURITY FIX: Enable proper authentication and authorization
    has_permission, user_data = auth_middleware.check_file_permissions(request, "view")
    if not has_permission:
        raise HTTPException(
            status_code=403, detail="Insufficient permissions for file operations"
        )

    # Store user data in request state for audit logging
    request.state.user = user_data

    target_path = validate_and_resolve_path(path)

    # Issue #358/#718: Use dedicated executor for non-blocking file I/O
    if not await run_in_file_executor(target_path.exists):
        raise HTTPException(status_code=404, detail="Directory not found")

    if not await run_in_file_executor(target_path.is_dir):
        raise HTTPException(status_code=400, detail="Path is not a directory")

    # Issue #358: Wrap blocking directory listing in thread
    def _list_directory_sync():
        """Sync helper for directory listing to avoid blocking event loop."""
        files = []
        total_size = 0
        total_files = 0
        total_directories = 0

        for item in sorted(
            target_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())
        ):
            try:
                relative_item_path = str(item.relative_to(SANDBOXED_ROOT))
                file_info = get_file_info(item, relative_item_path)
                files.append(file_info)

                if item.is_file():
                    total_files += 1
                    total_size += file_info.size or 0
                else:
                    total_directories += 1

            except (OSError, PermissionError) as e:
                logger.warning("Skipping inaccessible file %s: %s", item, e)
                continue

        return files, total_size, total_files, total_directories

    files, total_size, total_files, total_directories = await run_in_file_executor(
        _list_directory_sync
    )

    # Calculate parent path
    parent_path = None
    if path:
        parent = Path(path).parent
        parent_path = str(parent) if str(parent) != "." else ""

    return DirectoryListing(
        current_path=path,
        parent_path=parent_path,
        files=files,
        total_files=total_files,
        total_directories=total_directories,
        total_size=total_size,
    )


def validate_file_content(content: bytes, filename: str) -> bool:
    """
    Validate file content for security threats.

    Args:
        content: File content bytes
        filename: Original filename

    Returns:
        bool: True if content is safe, False otherwise
    """
    # Check for null bytes (potential binary injection)
    if b"\x00" in content:
        # Only allow null bytes in known binary formats
        extension = Path(filename).suffix.lower()
        binary_formats = {
            # Images
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".ico",
            # Documents (PDF)
            ".pdf",
            # Microsoft Office (ZIP-based binary formats)
            ".doc",
            ".docx",
            ".xlsx",
            ".ppt",
            ".pptx",
            # OpenDocument (ZIP-based binary formats)
            ".odt",
            ".ods",
            ".odp",
            ".odg",
        }
        if extension not in binary_formats:
            return False

    # Check for script tags and other dangerous content (Issue #380: use module constant)
    content_str = content.decode("utf-8", errors="ignore").lower()

    for pattern in _DANGEROUS_CONTENT_PATTERNS:
        if pattern in content_str:
            logger.warning("Dangerous content detected in %s: %s", filename, pattern)
            return False

    return True


def _validate_upload_file(file: UploadFile, content: bytes) -> None:
    """
    Validate uploaded file for security and constraints.

    Issue #281: Extracted helper for file validation.

    Args:
        file: Uploaded file object
        content: File content bytes

    Raises:
        HTTPException: If validation fails
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    if not is_safe_file(file.filename):
        raise HTTPException(
            status_code=400, detail=f"File type not allowed: {file.filename}"
        )

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB",
        )

    if not validate_file_content(content, file.filename):
        raise HTTPException(
            status_code=400,
            detail="File content contains potentially dangerous elements",
        )

    # Verify MIME type matches file extension
    detected_mime = mimetypes.guess_type(file.filename)[0]
    if detected_mime and file.content_type and file.content_type != detected_mime:
        logger.warning(
            f"MIME type mismatch for {file.filename}: "
            f"declared={file.content_type}, detected={detected_mime}"
        )


async def _write_upload_file(target_file: Path, content: bytes, overwrite: bool) -> None:
    """
    Write uploaded file to target location.

    Issue #281: Extracted helper for file writing.

    Args:
        target_file: Target file path
        content: File content to write
        overwrite: Whether to overwrite existing files

    Raises:
        HTTPException: If file exists without overwrite or write fails
    """
    # Issue #358: Check if file exists in thread to avoid blocking
    file_exists = await run_in_file_executor(target_file.exists)
    if file_exists and not overwrite:
        raise HTTPException(
            status_code=409,
            detail="File already exists. Use overwrite=true to replace it.",
        )

    try:
        async with aiofiles.open(target_file, "wb") as f:
            await f.write(content)
    except OSError as e:
        logger.error("Failed to write uploaded file %s: %s", target_file, e)
        raise HTTPException(status_code=500, detail=f"Failed to write file: {e}")


def _log_upload_audit(
    request: Request,
    user_data: dict,
    file: UploadFile,
    relative_path: str,
    content_size: int,
    overwrite: bool,
) -> None:
    """
    Log upload audit information.

    Issue #281: Extracted helper for audit logging.

    Args:
        request: FastAPI request
        user_data: Authenticated user data
        file: Uploaded file
        relative_path: Relative path to file
        content_size: Size of uploaded content
        overwrite: Whether overwrite was used
    """
    security_layer = get_security_layer(request)
    security_layer.audit_log(
        "file_upload",
        user_data.get("username", "unknown"),
        "success",
        {
            "filename": file.filename,
            "path": relative_path,
            "size": content_size,
            "user_role": user_data.get("role", "unknown"),
            "ip": request.client.host if request.client else "unknown",
            "overwrite": overwrite,
        },
    )


async def _delete_file_item(
    target_path: Path, path: str, security_layer, user_data: dict, request: Request
) -> dict:
    """
    Delete a single file and log audit.

    Issue #398: Extracted from delete_file to reduce method length.
    """
    file_stat = await run_in_file_executor(target_path.stat)
    file_size = file_stat.st_size
    await run_in_file_executor(target_path.unlink)

    security_layer.audit_log(
        "file_delete",
        user_data.get("username", "unknown"),
        "success",
        {
            "path": path,
            "type": "file",
            "size": file_size,
            "filename": target_path.name,
            "user_role": user_data.get("role", "unknown"),
            "ip": request.client.host if request.client else "unknown",
        },
    )
    return {"message": f"File '{target_path.name}' deleted successfully"}


async def _delete_directory_item(
    target_path: Path, path: str, security_layer, user_data: dict, request: Request
) -> dict:
    """
    Delete a directory (empty or recursively) and log audit.

    Issue #398: Extracted from delete_file to reduce method length.
    """
    try:
        await run_in_file_executor(target_path.rmdir)
        delete_type = "directory"
        extra = {}
    except OSError:
        await run_in_file_executor(shutil.rmtree, target_path)
        delete_type = "directory_recursive"
        extra = {"warning": "recursive_delete_performed"}

    security_layer.audit_log(
        "file_delete",
        user_data.get("username", "unknown"),
        "success",
        {
            "path": path,
            "type": delete_type,
            "dirname": target_path.name,
            "user_role": user_data.get("role", "unknown"),
            "ip": request.client.host if request.client else "unknown",
            **extra,
        },
    )

    if delete_type == "directory_recursive":
        return {
            "message": f"Directory '{target_path.name}' and all contents deleted successfully"
        }
    return {"message": f"Directory '{target_path.name}' deleted successfully"}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="upload_file",
    error_code_prefix="FILES",
)
@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    path: str = Form(""),
    overwrite: bool = Form(False),
):
    """
    Upload a file to the specified directory within the sandbox.

    Issue #281: Refactored from 115 lines to use extracted helper methods.

    Args:
        file: The file to upload
        path: Target directory path within sandbox
        overwrite: Whether to overwrite existing files
    """
    # SECURITY FIX: Enable proper authentication and authorization
    has_permission, user_data = auth_middleware.check_file_permissions(
        request, "upload"
    )
    if not has_permission:
        raise HTTPException(
            status_code=403, detail="Insufficient permissions for file upload"
        )

    # Store user data in request state for audit logging
    request.state.user = user_data

    # Read file content
    content = await file.read()

    # Validate file (Issue #281: uses helper)
    _validate_upload_file(file, content)

    # Validate and resolve target directory
    target_dir = validate_and_resolve_path(path)
    # Issue #358: mkdir in thread to avoid blocking
    await run_in_file_executor(lambda: target_dir.mkdir(parents=True, exist_ok=True))

    # Prepare target file path
    target_file = target_dir / file.filename

    # Write file (Issue #281: uses helper)
    await _write_upload_file(target_file, content, overwrite)

    # Get file info for response
    relative_path = str(target_file.relative_to(SANDBOXED_ROOT))
    file_info = get_file_info(target_file, relative_path)

    # Audit logging (Issue #281: uses helper)
    _log_upload_audit(request, user_data, file, relative_path, len(content), overwrite)

    return FileUploadResponse(
        success=True,
        message=f"File '{file.filename}' uploaded successfully",
        file_info=file_info,
        upload_id=f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="download_file",
    error_code_prefix="FILES",
)
@router.get("/download/{path:path}")
async def download_file(request: Request, path: str):
    """
    Download a file from the sandbox.

    Args:
        path: File path within the sandbox
    """
    # SECURITY FIX: Enable proper authentication and authorization
    has_permission, user_data = auth_middleware.check_file_permissions(
        request, "download"
    )
    if not has_permission:
        raise HTTPException(
            status_code=403, detail="Insufficient permissions for file download"
        )

    # Store user data in request state for audit logging
    request.state.user = user_data

    target_file = validate_and_resolve_path(path)

    # Issue #358/#718: Use dedicated executor for non-blocking file I/O
    if not await run_in_file_executor(target_file.exists):
        raise HTTPException(status_code=404, detail="File not found")

    if not await run_in_file_executor(target_file.is_file):
        raise HTTPException(status_code=400, detail="Path is not a file")

    # Issue #358: Get file stat in thread to avoid blocking
    file_stat = await run_in_file_executor(target_file.stat)

    # Enhanced audit logging with authenticated user
    security_layer = get_security_layer(request)
    security_layer.audit_log(
        "file_download",
        user_data.get("username", "unknown"),
        "success",
        {
            "path": path,
            "size": file_stat.st_size,
            "filename": target_file.name,
            "user_role": user_data.get("role", "unknown"),
            "ip": request.client.host if request.client else "unknown",
        },
    )

    return FileResponse(
        path=str(target_file),
        filename=target_file.name,
        media_type="application/octet-stream",
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="view_file",
    error_code_prefix="FILES",
)
@router.get("/view/{path:path}")
async def view_file(request: Request, path: str):
    """
    View file content (for text files) or get file info.

    Args:
        path: File path within the sandbox
    """
    # SECURITY FIX: Use modern auth_middleware instead of deprecated function
    has_permission, user_data = auth_middleware.check_file_permissions(request, "view")
    if not has_permission:
        raise HTTPException(
            status_code=403, detail="Insufficient permissions for file viewing"
        )

    # Store user data in request state for audit logging
    request.state.user = user_data

    target_file = validate_and_resolve_path(path)

    # Issue #358/#718: Use dedicated executor for non-blocking file I/O
    if not await run_in_file_executor(target_file.exists):
        raise HTTPException(status_code=404, detail="File not found")

    if not await run_in_file_executor(target_file.is_file):
        raise HTTPException(status_code=400, detail="Path is not a file")

    # Issue #358: Get file info in thread to avoid blocking
    relative_path = str(target_file.relative_to(SANDBOXED_ROOT))
    file_info = await run_in_file_executor(get_file_info, target_file, relative_path)

    # Try to read content for text files
    content = None
    if file_info.mime_type and file_info.mime_type.startswith("text/"):
        try:
            # PERFORMANCE FIX: Convert to async file I/O
            async with aiofiles.open(target_file, "r", encoding="utf-8") as f:
                content = await f.read()
        except OSError as e:
            logger.error("Failed to read file %s: %s", target_file, e)
            raise HTTPException(status_code=500, detail=f"Failed to read file: {e}")
        except UnicodeDecodeError as e:
            # File is binary, don't include content
            logger.debug("File is binary, skipping content read: %s", e)

    return {
        "file_info": file_info,
        "content": content,
        "is_text": content is not None,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="rename_file_or_directory",
    error_code_prefix="FILES",
)
@router.post("/rename")
async def rename_file_or_directory(
    request: Request, path: str = Form(...), new_name: str = Form(...)
):
    """
    Rename a file or directory within the sandbox.

    Args:
        path: Current path of the file/directory
        new_name: New name for the file/directory (not full path, just name)
    """
    # SECURITY FIX: Enable proper authentication and authorization
    has_permission, user_data = auth_middleware.check_file_permissions(
        request, "upload"  # Using upload permission for rename
    )
    if not has_permission:
        raise HTTPException(
            status_code=403, detail="Insufficient permissions for rename operation"
        )

    # Store user data in request state for audit logging
    request.state.user = user_data

    # Validate new name
    if is_invalid_name(new_name):
        raise HTTPException(status_code=400, detail="Invalid file/directory name")

    source_path = validate_and_resolve_path(path)

    # Issue #358/#718: Use dedicated executor for non-blocking file I/O
    if not await run_in_file_executor(source_path.exists):
        raise HTTPException(status_code=404, detail="File or directory not found")

    # Create new path with same parent directory
    target_path = source_path.parent / new_name

    if await run_in_file_executor(target_path.exists):
        raise HTTPException(
            status_code=409,
            detail=f"A file or directory named '{new_name}' already exists",
        )

    # Issue #358: Perform rename in thread to avoid blocking
    await run_in_file_executor(source_path.rename, target_path)

    # Issue #358: Get info for the renamed item in thread
    relative_path = str(target_path.relative_to(SANDBOXED_ROOT))
    item_info = await run_in_file_executor(get_file_info, target_path, relative_path)
    is_directory = await run_in_file_executor(target_path.is_dir)

    # Enhanced audit logging
    security_layer = get_security_layer(request)
    security_layer.audit_log(
        "file_rename",
        user_data.get("username", "unknown"),
        "success",
        {
            "old_path": path,
            "new_name": new_name,
            "new_path": relative_path,
            "type": "directory" if is_directory else "file",
            "user_role": user_data.get("role", "unknown"),
            "ip": request.client.host if request.client else "unknown",
        },
    )

    return {
        "message": f"Successfully renamed to '{new_name}'",
        "item_info": item_info,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="preview_file",
    error_code_prefix="FILES",
)
@router.get("/preview")
async def preview_file(request: Request, path: str):
    """
    Get file preview with content and download URL.

    Args:
        path: File path within the sandbox (query parameter)

    Returns:
        Dict with type, url, and content for preview
    """
    has_permission, user_data = auth_middleware.check_file_permissions(request, "view")
    if not has_permission:
        raise HTTPException(
            status_code=403, detail="Insufficient permissions for file preview"
        )

    request.state.user = user_data

    target_file = validate_and_resolve_path(path)

    # Issue #358/#718: Use dedicated executor for non-blocking file I/O
    if not await run_in_file_executor(target_file.exists):
        raise HTTPException(status_code=404, detail="File not found")

    if not await run_in_file_executor(target_file.is_file):
        raise HTTPException(status_code=400, detail="Path is not a file")

    # Issue #358: Get file info in thread to avoid blocking
    relative_path = str(target_file.relative_to(SANDBOXED_ROOT))
    file_info = await run_in_file_executor(get_file_info, target_file, relative_path)

    # Determine file type
    file_type = "binary"
    content = None

    if file_info.mime_type:
        if file_info.mime_type.startswith("text/"):
            file_type = "text"
            try:
                async with aiofiles.open(target_file, "r", encoding="utf-8") as f:
                    content = await f.read()
            except OSError as e:
                logger.error("Failed to read file %s: %s", target_file, e)
                raise HTTPException(status_code=500, detail=f"Failed to read file: {e}")
            except UnicodeDecodeError:
                file_type = "binary"
        elif file_info.mime_type.startswith("image/"):
            file_type = "image"
        elif file_info.mime_type == "application/pdf":
            file_type = "pdf"

    # Generate download URL
    download_url = f"/api/files/download/{path}"

    return {
        "type": file_type,
        "url": download_url,
        "content": content,
        "mime_type": file_info.mime_type,
        "size": file_info.size,
        "name": file_info.name,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_file",
    error_code_prefix="FILES",
)
@router.delete("/delete")
async def delete_file(request: Request, path: str):
    """
    Delete a file or directory within the sandbox.

    Issue #398: Refactored with extracted helper methods.

    Args:
        path: Path to the file/directory to delete (query parameter)
    """
    has_permission, user_data = auth_middleware.check_file_permissions(
        request, "delete"
    )
    if not has_permission:
        raise HTTPException(
            status_code=403, detail="Insufficient permissions for file deletion"
        )

    request.state.user = user_data
    target_path = validate_and_resolve_path(path)

    if not await run_in_file_executor(target_path.exists):
        raise HTTPException(status_code=404, detail="File or directory not found")

    security_layer = get_security_layer(request)
    is_file = await run_in_file_executor(target_path.is_file)

    if is_file:
        return await _delete_file_item(
            target_path, path, security_layer, user_data, request
        )
    return await _delete_directory_item(
        target_path, path, security_layer, user_data, request
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_directory",
    error_code_prefix="FILES",
)
@router.post("/create_directory")
async def create_directory(
    request: Request, path: str = Form(...), name: str = Form(...)
):
    """
    Create a new directory within the sandbox.

    Args:
        path: Parent directory path
        name: New directory name
    """
    # SECURITY FIX: Enable proper authentication and authorization
    has_permission, user_data = auth_middleware.check_file_permissions(
        request, "upload"
    )
    if not has_permission:
        raise HTTPException(
            status_code=403, detail="Insufficient permissions for directory creation"
        )

    # Store user data in request state for audit logging
    request.state.user = user_data

    # Validate directory name
    if is_invalid_name(name):
        raise HTTPException(status_code=400, detail="Invalid directory name")

    parent_dir = validate_and_resolve_path(path)
    new_dir = parent_dir / name

    # Issue #358/#718: Use dedicated executor for non-blocking file I/O
    if await run_in_file_executor(new_dir.exists):
        raise HTTPException(status_code=409, detail="Directory already exists")

    # Issue #358: mkdir in thread to avoid blocking
    await run_in_file_executor(lambda: new_dir.mkdir(parents=True, exist_ok=False))

    # Issue #358: Get directory info in thread to avoid blocking
    relative_path = str(new_dir.relative_to(SANDBOXED_ROOT))
    dir_info = await run_in_file_executor(get_file_info, new_dir, relative_path)

    # Enhanced audit logging with authenticated user
    security_layer = get_security_layer(request)
    security_layer.audit_log(
        "directory_create",
        user_data.get("username", "unknown"),
        "success",
        {
            "path": relative_path,
            "name": name,
            "parent_path": path,
            "user_role": user_data.get("role", "unknown"),
            "ip": request.client.host if request.client else "unknown",
        },
    )

    return {
        "message": f"Directory '{name}' created successfully",
        "directory_info": dir_info,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_directory_tree",
    error_code_prefix="FILES",
)
@router.get("/tree")
async def get_directory_tree(request: Request, path: str = ""):
    """Get directory tree structure for file browser"""
    # SECURITY FIX: Enable proper authentication and authorization
    has_permission, user_data = auth_middleware.check_file_permissions(request, "view")
    if not has_permission:
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions for viewing directory tree",
        )

    # Store user data in request state for audit logging
    request.state.user = user_data

    target_path = validate_and_resolve_path(path)

    # Issue #358/#718: Use dedicated executor for non-blocking file I/O
    if not await run_in_file_executor(target_path.exists):
        raise HTTPException(status_code=404, detail="Directory not found")

    if not await run_in_file_executor(target_path.is_dir):
        raise HTTPException(status_code=400, detail="Path is not a directory")

    def build_tree(directory: Path, relative_base: Path) -> dict:
        """Recursively build directory tree structure (sync, runs in thread)"""
        try:
            items = []
            for item in sorted(
                directory.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())
            ):
                try:
                    relative_path = str(item.relative_to(SANDBOXED_ROOT))
                    item_info = {
                        "name": item.name,
                        "path": relative_path,
                        "type": "directory" if item.is_dir() else "file",
                    }

                    if item.is_file():
                        item_info["size"] = item.stat().st_size
                        item_info["extension"] = (
                            item.suffix.lower() if item.suffix else None
                        )
                    else:
                        # Recursively add children for directories
                        item_info["children"] = build_tree(item, SANDBOXED_ROOT)

                    items.append(item_info)
                except (OSError, PermissionError) as e:
                    logger.warning("Skipping inaccessible item %s: %s", item, e)
                    continue

            return items
        except Exception as e:
            logger.error("Error building tree for %s: %s", directory, e)
            return []

    # Issue #358: Run entire recursive tree building in thread to avoid blocking
    tree_data = await run_in_file_executor(build_tree, target_path, SANDBOXED_ROOT)

    return {"path": path, "tree": tree_data}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_file_stats",
    error_code_prefix="FILES",
)
@router.get("/stats")
async def get_file_stats(request: Request):
    """Get file system statistics for the sandbox"""
    # SECURITY FIX: Enable proper authentication and authorization
    has_permission, user_data = auth_middleware.check_file_permissions(request, "view")
    if not has_permission:
        raise HTTPException(
            status_code=403, detail="Insufficient permissions for file statistics"
        )

    # Store user data in request state for audit logging
    request.state.user = user_data

    # Issue #358: Run stats collection in thread to avoid blocking event loop
    def _collect_stats_sync():
        """Sync helper for stats collection to avoid blocking event loop."""
        total_files = 0
        total_directories = 0
        total_size = 0

        for item in SANDBOXED_ROOT.rglob("*"):
            if item.is_file():
                total_files += 1
                total_size += item.stat().st_size
            elif item.is_dir():
                total_directories += 1

        return total_files, total_directories, total_size

    total_files, total_directories, total_size = await run_in_file_executor(
        _collect_stats_sync
    )

    return {
        "sandbox_root": str(SANDBOXED_ROOT),
        "total_files": total_files,
        "total_directories": total_directories,
        "total_size": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "max_file_size_mb": MAX_FILE_SIZE // (1024 * 1024),
        "allowed_extensions": sorted(list(ALLOWED_EXTENSIONS)),
    }
