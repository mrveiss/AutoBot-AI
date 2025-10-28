"""
Secure File Management API

This module provides secure file management endpoints with proper sandboxing,
path traversal protection, and authentication/authorization.
"""

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
from src.auth_middleware import auth_middleware
from src.constants.network_constants import NetworkConstants
from src.security_layer import SecurityLayer
from src.utils.error_boundaries import ErrorCategory, with_error_handling

router = APIRouter()
logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)

# Configure sandboxed directory for file operations using centralized paths

# Ensure data directory exists
ensure_data_directory()

# Get sandboxed root using centralized path management
SANDBOXED_ROOT = get_data_path("file_manager_root")
SANDBOXED_ROOT.mkdir(parents=True, exist_ok=True)

# Maximum file size (50MB)
MAX_FILE_SIZE = 50 * 1024 * 1024

# Allowed file extensions for security
ALLOWED_EXTENSIONS = {
    ".txt",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".py",
    ".js",
    ".ts",
    ".html",
    ".css",
    ".xml",
    ".csv",
    ".log",
    ".con",
    ".cfg",
    ".ini",
    ".sh",
    ".bat",
    ".sql",
    ".pd",
    ".png",
    ".jpg",
    ".jpeg",
    ".gi",
    ".svg",
    ".ico",
}


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
        if not v or ".." in v or v.startswith("/"):
            raise ValueError("Invalid path")
        return v


def get_security_layer(request: Request) -> SecurityLayer:
    """Get security layer from app state"""
    return request.app.state.security_layer


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
        or any(char in clean_path for char in ["<", ">", ":", '"', "|", "?", "*"])
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

    return full_path


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
    """Check if file type is allowed and filename is safe"""
    if not filename:
        return False

    # Check for dangerous characters in filename
    dangerous_chars = {"<", ">", '"', "|", "?", "*", "\0", "\r", "\n"}
    if any(char in filename for char in dangerous_chars):
        return False

    # Check filename length
    if len(filename) > 255:
        return False

    # Check extension
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        return False

    # Check for dangerous filenames
    dangerous_names = {
        ".htaccess",
        ".env",
        "passwd",
        "shadow",
        "config",
        "web.config",
        "autoexec.bat",
        "boot.ini",
        "hosts",
        "httpd.conf",
        "nginx.conf",
    }
    if filename.lower() in dangerous_names:
        return False

    # Check for executable extensions not in allowlist
    dangerous_extensions = {
        ".exe",
        ".bat",
        ".cmd",
        ".com",
        ".scr",
        ".pif",
        ".vbs",
        ".js",
        ".jar",
        ".app",
        ".deb",
        ".rpm",
        ".dmg",
        ".pkg",
        ".msi",
    }
    if extension in dangerous_extensions and extension not in ALLOWED_EXTENSIONS:
        return False

    # Prevent null bytes and control characters in filename
    if "\0" in filename or any(ord(c) < 32 for c in filename):
        return False

    return True


@router.get("/list", response_model=DirectoryListing)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_files",
    error_code_prefix="FILES",
)
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

    if not target_path.exists():
        raise HTTPException(status_code=404, detail="Directory not found")

    if not target_path.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")

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
            logger.warning(f"Skipping inaccessible file {item}: {e}")
            continue

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
        binary_formats = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf"}
        if extension not in binary_formats:
            return False

    # Check for script tags and other dangerous content
    content_str = content.decode("utf-8", errors="ignore").lower()
    dangerous_patterns = [
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
    ]

    for pattern in dangerous_patterns:
        if pattern in content_str:
            logger.warning(f"Dangerous content detected in {filename}: {pattern}")
            return False

    return True


@router.post("/upload", response_model=FileUploadResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="upload_file",
    error_code_prefix="FILES",
)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    path: str = Form(""),
    overwrite: bool = Form(False),
):
    """
    Upload a file to the specified directory within the sandbox.

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

    # Validate file
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    if not is_safe_file(file.filename):
        raise HTTPException(
            status_code=400, detail=f"File type not allowed: {file.filename}"
        )

    # Read and validate file content
    content = await file.read()

    # Check file size
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=(
                "File too large. Maximum size: " f"{MAX_FILE_SIZE // (1024*1024)}MB"
            ),
        )

    # Validate content for security threats
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

    # Validate and resolve target directory
    target_dir = validate_and_resolve_path(path)
    target_dir.mkdir(parents=True, exist_ok=True)

    # Prepare target file path
    target_file = target_dir / file.filename

    # Check if file exists and overwrite policy
    if target_file.exists() and not overwrite:
        raise HTTPException(
            status_code=409,
            detail="File already exists. Use overwrite=true to replace it.",
        )

    # Write file - PERFORMANCE FIX: Convert to async file I/O
    async with aiofiles.open(target_file, "wb") as f:
        await f.write(content)

    # Get file info for response
    relative_path = str(target_file.relative_to(SANDBOXED_ROOT))
    file_info = get_file_info(target_file, relative_path)

    # Enhanced audit logging with authenticated user
    security_layer = get_security_layer(request)
    security_layer.audit_log(
        "file_upload",
        user_data.get("username", "unknown"),
        "success",
        {
            "filename": file.filename,
            "path": relative_path,
            "size": len(content),
            "user_role": user_data.get("role", "unknown"),
            "ip": request.client.host if request.client else "unknown",
            "overwrite": overwrite,
        },
    )

    return FileUploadResponse(
        success=True,
        message=f"File '{file.filename}' uploaded successfully",
        file_info=file_info,
        upload_id=f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    )


@router.get("/download/{path:path}")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="download_file",
    error_code_prefix="FILES",
)
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

    if not target_file.exists():
        raise HTTPException(status_code=404, detail="File not found")

    if not target_file.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file")

    # Enhanced audit logging with authenticated user
    security_layer = get_security_layer(request)
    security_layer.audit_log(
        "file_download",
        user_data.get("username", "unknown"),
        "success",
        {
            "path": path,
            "size": target_file.stat().st_size,
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


@router.get("/view/{path:path}")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="view_file",
    error_code_prefix="FILES",
)
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

    if not target_file.exists():
        raise HTTPException(status_code=404, detail="File not found")

    if not target_file.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file")

    # Get file info
    relative_path = str(target_file.relative_to(SANDBOXED_ROOT))
    file_info = get_file_info(target_file, relative_path)

    # Try to read content for text files
    content = None
    if file_info.mime_type and file_info.mime_type.startswith("text/"):
        try:
            # PERFORMANCE FIX: Convert to async file I/O
            async with aiofiles.open(target_file, "r", encoding="utf-8") as f:
                content = await f.read()
        except UnicodeDecodeError:
            # File is binary, don't include content
            pass

    return {
        "file_info": file_info,
        "content": content,
        "is_text": content is not None,
    }


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

    try:
        # Validate new name
        if not new_name or "/" in new_name or "\\" in new_name or ".." in new_name:
            raise HTTPException(status_code=400, detail="Invalid file/directory name")

        source_path = validate_and_resolve_path(path)

        if not source_path.exists():
            raise HTTPException(status_code=404, detail="File or directory not found")

        # Create new path with same parent directory
        target_path = source_path.parent / new_name

        if target_path.exists():
            raise HTTPException(
                status_code=409, detail=f"A file or directory named '{new_name}' already exists"
            )

        # Perform rename
        source_path.rename(target_path)

        # Get info for the renamed item
        relative_path = str(target_path.relative_to(SANDBOXED_ROOT))
        item_info = get_file_info(target_path, relative_path)

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
                "type": "directory" if target_path.is_dir() else "file",
                "user_role": user_data.get("role", "unknown"),
                "ip": request.client.host if request.client else "unknown",
            },
        )

        return {
            "message": f"Successfully renamed to '{new_name}'",
            "item_info": item_info,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error renaming file/directory: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error renaming: {str(e)}"
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

    try:
        target_file = validate_and_resolve_path(path)

        if not target_file.exists():
            raise HTTPException(status_code=404, detail="File not found")

        if not target_file.is_file():
            raise HTTPException(status_code=400, detail="Path is not a file")

        # Get file info
        relative_path = str(target_file.relative_to(SANDBOXED_ROOT))
        file_info = get_file_info(target_file, relative_path)

        # Determine file type
        file_type = "binary"
        content = None

        if file_info.mime_type:
            if file_info.mime_type.startswith("text/"):
                file_type = "text"
                try:
                    async with aiofiles.open(target_file, "r", encoding="utf-8") as f:
                        content = await f.read()
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
            "name": file_info.name
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error previewing file: {e}")
        raise HTTPException(status_code=500, detail=f"Error previewing file: {str(e)}")


@router.delete("/delete")
async def delete_file(request: Request, path: str):
    """
    Delete a file or directory within the sandbox.

    Args:
        path: Path to the file/directory to delete (query parameter)
    """
    # SECURITY FIX: Enable proper authentication and authorization
    has_permission, user_data = auth_middleware.check_file_permissions(
        request, "delete"
    )
    if not has_permission:
        raise HTTPException(
            status_code=403, detail="Insufficient permissions for file deletion"
        )

    # Store user data in request state for audit logging
    request.state.user = user_data

    try:
        target_path = validate_and_resolve_path(path)

        if not target_path.exists():
            raise HTTPException(status_code=404, detail="File or directory not found")

        # Log the deletion attempt
        security_layer = get_security_layer(request)

        if target_path.is_file():
            file_size = target_path.stat().st_size
            target_path.unlink()
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
        else:
            # Delete directory (only if empty for safety)
            try:
                target_path.rmdir()
                security_layer.audit_log(
                    "file_delete",
                    user_data.get("username", "unknown"),
                    "success",
                    {
                        "path": path,
                        "type": "directory",
                        "dirname": target_path.name,
                        "user_role": user_data.get("role", "unknown"),
                        "ip": request.client.host if request.client else "unknown",
                    },
                )
                return {
                    "message": f"Directory '{target_path.name}' deleted successfully"
                }
            except OSError:
                # Directory not empty, use recursive delete with caution
                shutil.rmtree(target_path)
                security_layer.audit_log(
                    "file_delete",
                    user_data.get("username", "unknown"),
                    "success",
                    {
                        "path": path,
                        "type": "directory_recursive",
                        "dirname": target_path.name,
                        "user_role": user_data.get("role", "unknown"),
                        "ip": request.client.host if request.client else "unknown",
                        "warning": "recursive_delete_performed",
                    },
                )
                return {
                    "message": (
                        f"Directory '{target_path.name}' and all contents "
                        "deleted successfully"
                    )
                }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting file: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting file: {str(e)}")


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

    try:
        # Validate directory name
        if not name or "/" in name or "\\" in name or ".." in name:
            raise HTTPException(status_code=400, detail="Invalid directory name")

        parent_dir = validate_and_resolve_path(path)
        new_dir = parent_dir / name

        if new_dir.exists():
            raise HTTPException(status_code=409, detail="Directory already exists")

        new_dir.mkdir(parents=True, exist_ok=False)

        # Get directory info
        relative_path = str(new_dir.relative_to(SANDBOXED_ROOT))
        dir_info = get_file_info(new_dir, relative_path)

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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating directory: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error creating directory: {str(e)}"
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

    try:
        target_path = validate_and_resolve_path(path)

        if not target_path.exists():
            raise HTTPException(status_code=404, detail="Directory not found")

        if not target_path.is_dir():
            raise HTTPException(status_code=400, detail="Path is not a directory")

        def build_tree(directory: Path, relative_base: Path) -> dict:
            """Recursively build directory tree structure"""
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
                        logger.warning(f"Skipping inaccessible item {item}: {e}")
                        continue

                return items
            except Exception as e:
                logger.error(f"Error building tree for {directory}: {e}")
                return []

        tree_data = build_tree(target_path, SANDBOXED_ROOT)

        return {"path": path, "tree": tree_data}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting directory tree: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error getting directory tree: {str(e)}"
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

    try:
        total_files = 0
        total_directories = 0
        total_size = 0

        for item in SANDBOXED_ROOT.rglob("*"):
            if item.is_file():
                total_files += 1
                total_size += item.stat().st_size
            elif item.is_dir():
                total_directories += 1

        return {
            "sandbox_root": str(SANDBOXED_ROOT),
            "total_files": total_files,
            "total_directories": total_directories,
            "total_size": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "max_file_size_mb": MAX_FILE_SIZE // (1024 * 1024),
            "allowed_extensions": sorted(list(ALLOWED_EXTENSIONS)),
        }

    except Exception as e:
        logger.error(f"Error getting file stats: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error getting file stats: {str(e)}"
        )
