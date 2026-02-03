# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Conversation-Specific File Management API

Provides secure file management endpoints for conversation-scoped files with proper
session ownership validation, authentication, and authorization.
"""

import asyncio
import logging
import secrets
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

import aiofiles
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator

from src.auth_middleware import auth_middleware
from src.security_layer import SecurityLayer
from src.utils.error_boundaries import ErrorCategory, with_error_handling

router = APIRouter()
logger = logging.getLogger(__name__)

# Issue #380: Module-level frozenset for dangerous filename characters
_DANGEROUS_FILENAME_CHARS = frozenset({"<", ">", '"', "|", "?", "*", "\0", "\r", "\n"})

# Maximum file size (50MB) - consistent with general file API
MAX_FILE_SIZE = 50 * 1024 * 1024

# Allowed file extensions - consistent with general file API
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
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
}


class FileDestination(str, Enum):
    """File transfer destination options"""

    KNOWLEDGE_BASE = "kb"
    SHARED = "shared"


class ConversationFileInfo(BaseModel):
    """Conversation file information model"""

    file_id: str
    filename: str
    original_filename: str
    size: int
    mime_type: Optional[str] = None
    session_id: str
    uploaded_at: datetime
    uploaded_by: str
    file_path: str
    extension: Optional[str] = None


class ConversationFileListResponse(BaseModel):
    """Response model for listing conversation files"""

    session_id: str
    files: List[ConversationFileInfo]
    total_files: int
    total_size: int
    page: int = 1
    page_size: int = 50


class FileUploadResponse(BaseModel):
    """Response model for file upload"""

    success: bool
    message: str
    file_info: Optional[ConversationFileInfo] = None
    upload_id: str


class FileTransferRequest(BaseModel):
    """Request model for file transfer operation"""

    file_ids: List[str] = Field(
        ..., min_items=1, description="List of file IDs to transfer"
    )
    destination: FileDestination = Field(
        ..., description="Transfer destination (kb or shared)"
    )
    target_path: Optional[str] = Field(None, description="Target path in destination")
    copy: bool = Field(False, description="Copy instead of move")
    tags: Optional[List[str]] = Field(None, description="Tags for KB indexing")

    @field_validator("file_ids")
    @classmethod
    def validate_file_ids(cls, v):
        """Validate that at least one file ID is provided."""
        if not v:
            raise ValueError("At least one file ID must be provided")
        return v


class FileTransferResponse(BaseModel):
    """Response model for file transfer operation"""

    success: bool
    message: str
    transferred_files: List[Dict[str, str]]
    failed_files: List[Dict[str, str]]
    total_transferred: int
    total_failed: int


class FilePreviewResponse(BaseModel):
    """Response model for file preview"""

    file_info: ConversationFileInfo
    preview_available: bool
    preview_content: Optional[str] = None
    preview_type: Optional[str] = None  # "text", "image", "metadata_only"


def get_security_layer(request: Request) -> SecurityLayer:
    """Get security layer from app state"""
    return request.app.state.security_layer


async def _authorize_file_operation(
    request: Request, session_id: str, operation: str
) -> dict:
    """Authorize file operation and return user data (Issue #398: extracted)."""
    has_permission, user_data = auth_middleware.check_file_permissions(
        request, operation
    )
    if not has_permission:
        raise HTTPException(
            status_code=403, detail=f"Insufficient permissions for file {operation}"
        )
    request.state.user = user_data
    await validate_session_ownership(request, session_id, user_data)
    return user_data


def _get_required_file_manager(request: Request):
    """Get file manager or raise 503 if unavailable (Issue #398: extracted)."""
    file_manager = get_conversation_file_manager(request)
    if not file_manager:
        logger.error("ConversationFileManager not available")
        raise HTTPException(
            status_code=503, detail="File management service temporarily unavailable"
        )
    return file_manager


def _audit_file_operation(
    request: Request, action: str, user_data: dict, session_id: str, details: dict
) -> None:
    """Log file operation to audit log (Issue #398: extracted)."""
    security_layer = get_security_layer(request)
    full_details = {
        "session_id": session_id,
        "ip": request.client.host if request.client else "unknown",
        **details,
    }
    security_layer.audit_log(
        action=action,
        user=user_data.get("username", "unknown"),
        outcome="success",
        details=full_details,
    )


def get_conversation_file_manager(request: Request):
    """
    Get ConversationFileManager from app state.

    Returns the conversation file manager instance initialized in lifespan.py.
    Returns None if not yet initialized (startup phase).
    """
    return getattr(request.app.state, "conversation_file_manager", None)


def get_chat_history_manager(request: Request):
    """Get chat history manager from app state for session validation"""
    return request.app.state.chat_history_manager


async def validate_session_ownership(
    request: Request, session_id: str, user_data: Dict
) -> bool:
    """
    Validate that the authenticated user owns the conversation session

    Args:
        request: FastAPI request object
        session_id: Conversation session ID
        user_data: Authenticated user data from auth middleware

    Returns:
        bool: True if user owns session, raises HTTPException otherwise
    """
    try:
        chat_history_manager = get_chat_history_manager(request)

        # Admin users can access all sessions
        # Issue #744: Require explicit role - no guest fallback for security
        user_role = user_data.get("role")
        if not user_role:
            raise HTTPException(
                status_code=403, detail="User role not assigned - access denied"
            )
        if user_role == "admin":
            logger.debug(
                f"Admin user {user_data.get('username')} accessing session {session_id}"
            )
            return True

        # Validate session ownership
        session_owner = await chat_history_manager.get_session_owner(session_id)
        current_user = user_data.get("username")

        # If session has no owner set, allow access (legacy sessions)
        if session_owner is None:
            logger.info(
                f"Session {session_id} has no owner - allowing access (legacy session)"
            )
            return True

        # Verify current user matches session owner
        if session_owner != current_user:
            logger.warning(
                f"Access denied: User {current_user} attempted to access "
                f"session {session_id} owned by {session_owner}"
            )
            raise HTTPException(
                status_code=403, detail="Access denied: You do not own this session"
            )

        logger.debug(
            "User %s validated as owner of session %s", current_user, session_id
        )
        return True

    except HTTPException:
        # Re-raise HTTP exceptions (403 Forbidden)
        raise
    except Exception as e:
        logger.error("Session ownership validation error: %s", e)
        raise HTTPException(
            status_code=500, detail="Failed to validate session ownership"
        )


def is_safe_file(filename: str) -> bool:
    """
    Check if file type is allowed and filename is safe
    Reuses validation logic from general file API
    """
    if not filename:
        return False

    # Check for dangerous characters (Issue #380: use module-level constant)
    if any(char in filename for char in _DANGEROUS_FILENAME_CHARS):
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
    }
    if filename.lower() in dangerous_names:
        return False

    # Prevent null bytes and control characters
    if "\0" in filename or any(ord(c) < 32 for c in filename):
        return False

    return True


async def _validate_and_read_upload_file(
    file: UploadFile,
) -> bytes:
    """
    Validate and read uploaded file content.

    Issue #281: Extracted from upload_conversation_file to reduce function
    length and improve reusability of validation logic.

    Args:
        file: Uploaded file object

    Returns:
        File content as bytes

    Raises:
        HTTPException: If validation fails (400, 413)
    """
    # Validate filename
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    if not is_safe_file(file.filename):
        raise HTTPException(
            status_code=400, detail=f"File type not allowed: {file.filename}"
        )

    # Read file content
    content = await file.read()

    # Check file size
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB",
        )

    return content


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="upload_conversation_file",
    error_code_prefix="CONVERSATION_FILES",
)
@router.post("/conversation/{session_id}/upload", response_model=FileUploadResponse)
async def upload_conversation_file(
    request: Request,
    session_id: str,
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
):
    """Upload a file to a conversation session (Issue #398: refactored)."""
    try:
        user_data = await _authorize_file_operation(request, session_id, "upload")
        content = await _validate_and_read_upload_file(file)
        file_manager = _get_required_file_manager(request)

        file_info_dict = await file_manager.upload_file(
            session_id=session_id,
            filename=file.filename,
            content=content,
            user_id=user_data.get("username"),
            description=description,
        )
        file_info = ConversationFileInfo(**file_info_dict)

        _audit_file_operation(
            request,
            "conversation_file_upload",
            user_data,
            session_id,
            {
                "filename": file.filename,
                "file_id": file_info.file_id,
                "size": len(content),
            },
        )

        upload_id = (
            f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(4)}"
        )

        return FileUploadResponse(
            success=True,
            message=f"File '{file.filename}' uploaded successfully to conversation",
            file_info=file_info,
            upload_id=upload_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error uploading conversation file: %s", e)
        raise HTTPException(status_code=500, detail=f"Error uploading file: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_conversation_files",
    error_code_prefix="CONVERSATION_FILES",
)
@router.get(
    "/conversation/{session_id}/list", response_model=ConversationFileListResponse
)
async def list_conversation_files(
    request: Request, session_id: str, page: int = 1, page_size: int = 50
):
    """
    List all files in a conversation session

    Args:
        session_id: Conversation session ID
        page: Page number for pagination
        page_size: Number of files per page

    Returns:
        ConversationFileListResponse with file list

    Raises:
        403: Insufficient permissions or not session owner
        404: Session not found
        500: Server error
    """
    # Authenticate and authorize
    has_permission, user_data = auth_middleware.check_file_permissions(request, "view")
    if not has_permission:
        raise HTTPException(
            status_code=403, detail="Insufficient permissions for file listing"
        )

    request.state.user = user_data

    try:
        # Validate session ownership
        await validate_session_ownership(request, session_id, user_data)

        # Get conversation file manager
        file_manager = get_conversation_file_manager(request)
        if not file_manager:
            logger.error("ConversationFileManager not available")
            raise HTTPException(
                status_code=503,
                detail="File management service temporarily unavailable",
            )

        # Get file list
        result = await file_manager.list_files(
            session_id=session_id, page=page, page_size=page_size
        )

        # Convert to Pydantic models
        files = [ConversationFileInfo(**f) for f in result["files"]]

        return ConversationFileListResponse(
            session_id=session_id,
            files=files,
            total_files=result["total_files"],
            total_size=result["total_size"],
            page=page,
            page_size=page_size,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error listing conversation files: %s", e)
        raise HTTPException(status_code=500, detail=f"Error listing files: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="download_conversation_file",
    error_code_prefix="CONVERSATION_FILES",
)
@router.get("/conversation/{session_id}/download/{file_id}")
async def download_conversation_file(request: Request, session_id: str, file_id: str):
    """
    Download a specific file from a conversation

    Args:
        session_id: Conversation session ID
        file_id: File ID to download

    Returns:
        FileResponse with file content

    Raises:
        403: Insufficient permissions or not session owner
        404: File not found
        500: Server error
    """
    # Authenticate and authorize
    has_permission, user_data = auth_middleware.check_file_permissions(
        request, "download"
    )
    if not has_permission:
        raise HTTPException(
            status_code=403, detail="Insufficient permissions for file download"
        )

    request.state.user = user_data

    try:
        # Validate session ownership
        await validate_session_ownership(request, session_id, user_data)

        # Get conversation file manager
        file_manager = get_conversation_file_manager(request)
        if not file_manager:
            logger.error("ConversationFileManager not available")
            raise HTTPException(
                status_code=503,
                detail="File management service temporarily unavailable",
            )

        # Get file info and path
        file_info_dict = await file_manager.get_file_info(session_id, file_id)
        if not file_info_dict:
            raise HTTPException(status_code=404, detail="File not found")

        file_path = Path(file_info_dict["file_path"])
        # Issue #358: Use asyncio.to_thread for blocking file I/O
        if not await asyncio.to_thread(file_path.exists):
            raise HTTPException(status_code=404, detail="File not found on disk")

        # Audit log
        security_layer = get_security_layer(request)
        security_layer.audit_log(
            action="conversation_file_download",
            user=user_data.get("username", "unknown"),
            outcome="success",
            details={
                "session_id": session_id,
                "file_id": file_id,
                "filename": file_info_dict["filename"],
                "size": file_info_dict["size"],
                "ip": request.client.host if request.client else "unknown",
            },
        )

        return FileResponse(
            path=str(file_path),
            filename=file_info_dict["original_filename"],
            media_type=file_info_dict.get("mime_type", "application/octet-stream"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error downloading conversation file: %s", e)
        raise HTTPException(status_code=500, detail=f"Error downloading file: {str(e)}")


async def _generate_file_preview(
    file_info: ConversationFileInfo,
) -> tuple[Optional[str], str, bool]:
    """
    Generate preview content based on file type.

    Issue #665: Extracted from preview_conversation_file to improve maintainability.
    Handles text file reading and image type detection for preview generation.

    Args:
        file_info: File information including path and MIME type.

    Returns:
        Tuple of (preview_content, preview_type, preview_available).
        - preview_content: Text content for text files, None otherwise
        - preview_type: "text", "image", or "metadata_only"
        - preview_available: True if preview can be shown
    """
    file_path = Path(file_info.file_path)
    preview_content = None
    preview_type = "metadata_only"
    preview_available = False

    if file_info.mime_type and file_info.mime_type.startswith("text/"):
        try:
            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                # Read first 10KB for preview
                preview_content = await f.read(10240)
                preview_type = "text"
                preview_available = True
        except (UnicodeDecodeError, OSError, IOError) as e:
            # File is binary or unreadable
            logger.debug("File is binary or unreadable, skipping preview: %s", e)
    elif file_info.mime_type and file_info.mime_type.startswith("image/"):
        preview_type = "image"
        preview_available = True
        # Image preview would return URL or base64 in production

    return preview_content, preview_type, preview_available


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="preview_conversation_file",
    error_code_prefix="CONVERSATION_FILES",
)
@router.get(
    "/conversation/{session_id}/preview/{file_id}", response_model=FilePreviewResponse
)
async def preview_conversation_file(request: Request, session_id: str, file_id: str):
    """
    Preview a file or get its metadata.

    Issue #665: Refactored to use _generate_file_preview helper.

    Args:
        session_id: Conversation session ID
        file_id: File ID to preview

    Returns:
        FilePreviewResponse with preview content or metadata

    Raises:
        403: Insufficient permissions or not session owner
        404: File not found
        500: Server error
    """
    # Authenticate and authorize
    has_permission, user_data = auth_middleware.check_file_permissions(request, "view")
    if not has_permission:
        raise HTTPException(
            status_code=403, detail="Insufficient permissions for file preview"
        )

    request.state.user = user_data

    try:
        # Validate session ownership
        await validate_session_ownership(request, session_id, user_data)

        # Get conversation file manager
        file_manager = get_conversation_file_manager(request)
        if not file_manager:
            logger.error("ConversationFileManager not available")
            raise HTTPException(
                status_code=503,
                detail="File management service temporarily unavailable",
            )

        # Get file info
        file_info_dict = await file_manager.get_file_info(session_id, file_id)
        if not file_info_dict:
            raise HTTPException(status_code=404, detail="File not found")

        file_info = ConversationFileInfo(**file_info_dict)

        # Generate preview (Issue #665: use extracted helper)
        preview_content, preview_type, preview_available = await _generate_file_preview(
            file_info
        )

        return FilePreviewResponse(
            file_info=file_info,
            preview_available=preview_available,
            preview_content=preview_content,
            preview_type=preview_type,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error previewing conversation file: %s", e)
        raise HTTPException(status_code=500, detail=f"Error previewing file: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_conversation_file",
    error_code_prefix="CONVERSATION_FILES",
)
@router.delete("/conversation/{session_id}/files/{file_id}")
async def delete_conversation_file(request: Request, session_id: str, file_id: str):
    """
    Delete a specific file from a conversation

    Args:
        session_id: Conversation session ID
        file_id: File ID to delete

    Returns:
        Success message with deleted file info

    Raises:
        403: Insufficient permissions or not session owner
        404: File not found
        500: Server error
    """
    # Authenticate and authorize
    has_permission, user_data = auth_middleware.check_file_permissions(
        request, "delete"
    )
    if not has_permission:
        raise HTTPException(
            status_code=403, detail="Insufficient permissions for file deletion"
        )

    request.state.user = user_data

    try:
        # Validate session ownership
        await validate_session_ownership(request, session_id, user_data)

        # Get conversation file manager
        file_manager = get_conversation_file_manager(request)
        if not file_manager:
            logger.error("ConversationFileManager not available")
            raise HTTPException(
                status_code=503,
                detail="File management service temporarily unavailable",
            )

        # Delete file
        deleted = await file_manager.delete_file(session_id, file_id)

        if not deleted:
            raise HTTPException(status_code=404, detail="File not found")

        # Audit log
        security_layer = get_security_layer(request)
        security_layer.audit_log(
            action="conversation_file_delete",
            user=user_data.get("username", "unknown"),
            outcome="success",
            details={
                "session_id": session_id,
                "file_id": file_id,
                "ip": request.client.host if request.client else "unknown",
            },
        )

        return JSONResponse(
            content={
                "success": True,
                "message": "File deleted successfully",
                "session_id": session_id,
                "file_id": file_id,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error deleting conversation file: %s", e)
        raise HTTPException(status_code=500, detail=f"Error deleting file: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="transfer_conversation_files",
    error_code_prefix="CONVERSATION_FILES",
)
@router.post("/conversation/{session_id}/transfer", response_model=FileTransferResponse)
async def transfer_conversation_files(
    request: Request, session_id: str, transfer_request: FileTransferRequest
):
    """Transfer files from conversation to knowledge base or shared storage (Issue #398: refactored)."""
    try:
        user_data = await _authorize_file_operation(request, session_id, "upload")
        file_manager = _get_required_file_manager(request)

        result = await file_manager.transfer_files(
            session_id=session_id,
            file_ids=transfer_request.file_ids,
            destination=transfer_request.destination.value,
            target_path=transfer_request.target_path,
            copy=transfer_request.copy,
            tags=transfer_request.tags,
            user_id=user_data.get("username"),
        )

        _audit_file_operation(
            request,
            "conversation_files_transfer",
            user_data,
            session_id,
            {
                "destination": transfer_request.destination.value,
                "file_count": len(transfer_request.file_ids),
                "transferred": result["total_transferred"],
                "failed": result["total_failed"],
                "copy": transfer_request.copy,
            },
        )

        return FileTransferResponse(
            success=result["total_failed"] == 0,
            message=f"Transferred {result['total_transferred']} files, {result['total_failed']} failed",
            transferred_files=result["transferred_files"],
            failed_files=result["failed_files"],
            total_transferred=result["total_transferred"],
            total_failed=result["total_failed"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error transferring conversation files: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Error transferring files: {str(e)}"
        )
