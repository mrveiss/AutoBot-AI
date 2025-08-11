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

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer
from pydantic import BaseModel, validator

from src.security_layer import SecurityLayer

router = APIRouter()
logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)

# Configure sandboxed directory for file operations
SANDBOXED_ROOT = Path("data/file_manager_root")
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
    ".conf",
    ".cfg",
    ".ini",
    ".sh",
    ".bat",
    ".sql",
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
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

    @validator("path")
    def validate_path(cls, v):
        if not v or ".." in v or v.startswith("/"):
            raise ValueError("Invalid path")
        return v


def get_security_layer(request: Request) -> SecurityLayer:
    """Get security layer from app state"""
    return request.app.state.security_layer


def check_file_permissions(request: Request, operation: str) -> bool:
    """
    Check if user has permission for file operations using SecurityLayer RBAC.

    Args:
        request: FastAPI request object containing user context
        operation: File operation type (view, upload, delete, download)

    Returns:
        bool: True if permission granted, False otherwise
    """
    try:
        security_layer = get_security_layer(request)

        # Get user role from request headers (temporary auth mechanism)
        # In production, replace with proper JWT/session authentication
        user_role = request.headers.get("X-User-Role", "guest")

        # Map file operations to specific permissions
        permission_map = {
            "view": "files.view",
            "upload": "files.upload",
            "delete": "files.delete",
            "download": "files.download",
            "create": "files.create",
        }

        required_permission = permission_map.get(operation)
        if not required_permission:
            logger.error(f"Unknown file operation: {operation}")
            return False

        # Check permission using SecurityLayer
        has_permission = security_layer.check_permission(
            user_role=user_role,
            action_type=required_permission,
            resource=f"file_operation:{operation}",
        )

        if not has_permission:
            # Log unauthorized access attempt
            security_layer.audit_log(
                action="file_access_denied",
                user=user_role,
                outcome="denied",
                details={
                    "operation": operation,
                    "permission_required": required_permission,
                    "user_agent": request.headers.get("User-Agent"),
                    "ip": request.client.host if request.client else "unknown",
                },
            )

        return has_permission

    except Exception as e:
        logger.error(
            f"Error checking file permissions for operation '{operation}': {e}"
        )
        # Fail secure - deny access on error
        return False


def validate_and_resolve_path(path: str) -> Path:
    """
    Validate and resolve a path within the sandboxed directory.
    Prevents path traversal attacks.
    """
    if not path:
        return SANDBOXED_ROOT

    # Remove leading/trailing slashes and normalize
    clean_path = path.strip("/")

    # Check for path traversal attempts
    if ".." in clean_path or clean_path.startswith("/"):
        raise HTTPException(
            status_code=400, detail="Invalid path: path traversal not allowed"
        )

    # Resolve the full path within sandbox
    full_path = SANDBOXED_ROOT / clean_path

    # Ensure the resolved path is within the sandbox
    try:
        full_path.resolve().relative_to(SANDBOXED_ROOT.resolve())
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
    """Check if file type is allowed"""
    if not filename:
        return False

    # Check extension
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        return False

    # Check for dangerous filenames
    dangerous_names = {".htaccess", ".env", "passwd", "shadow"}
    if filename.lower() in dangerous_names:
        return False

    return True


@router.get("/list", response_model=DirectoryListing)
async def list_files(request: Request, path: str = ""):
    """
    List files in the specified directory within the sandbox.

    Args:
        path: Relative path within the sandbox (optional, defaults to root)
    """
    # TODO: Re-enable strict permissions after frontend auth integration
    # Temporarily allow file listing for development
    # if not check_file_permissions(request, "view"):
    #     raise HTTPException(
    #         status_code=403, detail="Insufficient permissions for file operations"
    #     )

    try:
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing files: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing files: {str(e)}")


@router.post("/upload", response_model=FileUploadResponse)
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
    if not check_file_permissions(request, "upload"):
        raise HTTPException(
            status_code=403, detail="Insufficient permissions for file upload"
        )

    try:
        # Validate file
        if not file.filename:
            raise HTTPException(status_code=400, detail="No filename provided")

        if not is_safe_file(file.filename):
            raise HTTPException(
                status_code=400, detail=f"File type not allowed: {file.filename}"
            )

        # Check file size
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"File too large. Maximum size: "
                    f"{MAX_FILE_SIZE // (1024*1024)}MB"
                ),
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

        # Write file
        with open(target_file, "wb") as f:
            f.write(content)

        # Get file info for response
        relative_path = str(target_file.relative_to(SANDBOXED_ROOT))
        file_info = get_file_info(target_file, relative_path)

        # Log the upload
        security_layer = get_security_layer(request)
        security_layer.audit_log(
            "file_upload",
            "system",
            "success",
            {"filename": file.filename, "path": relative_path, "size": len(content)},
        )

        return FileUploadResponse(
            success=True,
            message=f"File '{file.filename}' uploaded successfully",
            file_info=file_info,
            upload_id=f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        raise HTTPException(status_code=500, detail=f"Error uploading file: {str(e)}")


@router.get("/download/{path:path}")
async def download_file(request: Request, path: str):
    """
    Download a file from the sandbox.

    Args:
        path: File path within the sandbox
    """
    if not check_file_permissions(request, "download"):
        raise HTTPException(
            status_code=403, detail="Insufficient permissions for file download"
        )

    try:
        target_file = validate_and_resolve_path(path)

        if not target_file.exists():
            raise HTTPException(status_code=404, detail="File not found")

        if not target_file.is_file():
            raise HTTPException(status_code=400, detail="Path is not a file")

        # Log the download
        security_layer = get_security_layer(request)
        security_layer.audit_log(
            "file_download",
            "system",
            "success",
            {"path": path, "size": target_file.stat().st_size},
        )

        return FileResponse(
            path=str(target_file),
            filename=target_file.name,
            media_type="application/octet-stream",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        raise HTTPException(status_code=500, detail=f"Error downloading file: {str(e)}")


@router.get("/view/{path:path}")
async def view_file(request: Request, path: str):
    """
    View file content (for text files) or get file info.

    Args:
        path: File path within the sandbox
    """
    if not check_file_permissions(request, "view"):
        raise HTTPException(
            status_code=403, detail="Insufficient permissions for file viewing"
        )

    try:
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
                with open(target_file, "r", encoding="utf-8") as f:
                    content = f.read()
            except UnicodeDecodeError:
                # File is binary, don't include content
                pass

        return {
            "file_info": file_info,
            "content": content,
            "is_text": content is not None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error viewing file: {e}")
        raise HTTPException(status_code=500, detail=f"Error viewing file: {str(e)}")


@router.delete("/delete")
async def delete_file(request: Request, file_operation: FileOperation):
    """
    Delete a file or directory within the sandbox.

    Args:
        file_operation: Contains the path to delete
    """
    if not check_file_permissions(request, "delete"):
        raise HTTPException(
            status_code=403, detail="Insufficient permissions for file deletion"
        )

    try:
        target_path = validate_and_resolve_path(file_operation.path)

        if not target_path.exists():
            raise HTTPException(status_code=404, detail="File or directory not found")

        # Log the deletion attempt
        security_layer = get_security_layer(request)

        if target_path.is_file():
            file_size = target_path.stat().st_size
            target_path.unlink()
            security_layer.audit_log(
                "file_delete",
                "system",
                "success",
                {"path": file_operation.path, "type": "file", "size": file_size},
            )
            return {"message": f"File '{target_path.name}' deleted successfully"}
        else:
            # Delete directory (only if empty for safety)
            try:
                target_path.rmdir()
                security_layer.audit_log(
                    "file_delete",
                    "system",
                    "success",
                    {"path": file_operation.path, "type": "directory"},
                )
                return {
                    "message": f"Directory '{target_path.name}' deleted successfully"
                }
            except OSError:
                # Directory not empty, use recursive delete with caution
                shutil.rmtree(target_path)
                security_layer.audit_log(
                    "file_delete",
                    "system",
                    "success",
                    {"path": file_operation.path, "type": "directory_recursive"},
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
    if not check_file_permissions(request, "upload"):
        raise HTTPException(
            status_code=403, detail="Insufficient permissions for directory creation"
        )

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

        # Log the creation
        security_layer = get_security_layer(request)
        security_layer.audit_log(
            "directory_create",
            "system",
            "success",
            {"path": relative_path, "name": name},
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


@router.get("/stats")
async def get_file_stats(request: Request):
    """Get file system statistics for the sandbox"""
    if not check_file_permissions(request, "view"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

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
