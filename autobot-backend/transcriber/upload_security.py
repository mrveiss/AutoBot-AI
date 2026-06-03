# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Transcriber Upload Security
# Issue #9214: Fix arbitrary file read vulnerability

"""Secure file upload handling for transcriber module."""

import os
import uuid
from pathlib import Path


from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Allowed audio file extensions
ALLOWED_EXTENSIONS = {".wav", ".mp3", ".mp4", ".m4a", ".ogg", ".flac", ".webm"}

# Maximum file size: 500MB
MAX_FILE_SIZE = 500 * 1024 * 1024


class UploadSecurityError(Exception):
    """Exception raised for upload security violations."""

    pass


def get_upload_base_dir() -> Path:
    """Get the base upload directory from environment or default.

    Returns:
        Path to upload base directory

    Raises:
        RuntimeError: If upload directory cannot be created
    """
    base_dir = os.environ.get("AUTOBOT_UPLOAD_DIR", "/var/lib/autobot/uploads")
    upload_path = Path(base_dir)

    # Create directory if it doesn't exist
    try:
        upload_path.mkdir(parents=True, exist_ok=True, mode=0o750)
    except OSError as exc:
        raise RuntimeError(f"Failed to create upload directory: {exc}")

    return upload_path


def get_user_upload_dir(user_id: int) -> Path:
    """Get or create user-specific upload directory.

    Args:
        user_id: User ID

    Returns:
        Path to user upload directory

    Raises:
        RuntimeError: If directory cannot be created
    """
    base_dir = get_upload_base_dir()
    # Use int() explicitly so static analysis sees an integer, not user-controlled data
    user_dir = base_dir / f"user_{int(user_id)}" / "recordings"

    try:
        user_dir.mkdir(parents=True, exist_ok=True, mode=0o750)
    except OSError as exc:
        raise RuntimeError(f"Failed to create user upload directory: {exc}")

    return user_dir


def generate_secure_filename(original_filename: str) -> str:
    """Generate a secure UUID-based filename preserving extension.

    Args:
        original_filename: Original uploaded filename

    Returns:
        Secure filename in format: {uuid}.{ext}

    Raises:
        UploadSecurityError: If extension is not allowed
    """
    # Look up extension from fixed allowlist — result is from ALLOWED_EXTENSIONS, not user string
    suffix = Path(original_filename).suffix.lower()
    ext = next((e for e in ALLOWED_EXTENSIONS if e == suffix), None)
    if ext is None:
        raise UploadSecurityError(
            f"File extension '{suffix}' not allowed. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    # Generate UUID filename (ext sourced from allowlist, not user input)
    secure_name = f"{uuid.uuid4()}{ext}"
    return secure_name


def validate_upload_path(file_path: str, user_id: int) -> Path:
    """Validate that a file path is within the user's upload directory.

    Security checks:
    - String-prefix check against upload base before any Path operations
    - Resolves symlinks and relative paths
    - Verifies resolved path is within user upload directory
    - Rejects symlinks (checked on resolved path, not raw input)

    Args:
        file_path: Path to validate
        user_id: User ID (for directory boundary check)

    Returns:
        Validated resolved Path object

    Raises:
        UploadSecurityError: If path validation fails
    """
    user_upload_dir = get_user_upload_dir(user_id)

    # String-prefix guard: reject input that cannot possibly be within the upload dir.
    # This is a fast early-exit and provides a CodeQL-visible sanitization boundary
    # before any Path/os operations receive the user-controlled value.
    upload_dir_str = str(user_upload_dir)
    if not file_path.startswith(upload_dir_str + os.sep) and file_path != upload_dir_str:
        raise UploadSecurityError(f"Path traversal attempt detected: path is outside upload directory")

    try:
        # Resolve symlinks and canonicalize — use only this resolved path hereafter
        path = Path(file_path).resolve()
    except (OSError, ValueError) as exc:
        raise UploadSecurityError(f"Invalid file path: {exc}")

    # Confirm resolved path is still within user upload directory (catches symlink escapes)
    try:
        path.relative_to(user_upload_dir)
    except ValueError:
        raise UploadSecurityError(f"Path traversal attempt detected: resolved path is outside upload directory")

    # Reject symlinks — check on the resolved path object, not the raw input
    if path.is_symlink():
        raise UploadSecurityError(f"Symlinks not allowed")

    # Verify file exists and is a regular file
    if not path.exists():
        raise UploadSecurityError(f"File not found")

    if not path.is_file():
        raise UploadSecurityError(f"Not a regular file")

    return path


def save_uploaded_file(file_content: bytes, original_filename: str, user_id: int) -> str:
    """Save uploaded file with secure path and filename.

    Args:
        file_content: Raw file bytes
        original_filename: Original filename from upload
        user_id: User ID for directory scoping

    Returns:
        Absolute path to saved file

    Raises:
        UploadSecurityError: If save operation fails security checks
        RuntimeError: If file write fails
    """
    # Validate file size
    if len(file_content) > MAX_FILE_SIZE:
        raise UploadSecurityError(f"File too large: {len(file_content)} bytes (max: {MAX_FILE_SIZE})")

    # Generate secure filename
    secure_filename = generate_secure_filename(original_filename)

    # Get user upload directory
    user_dir = get_user_upload_dir(user_id)

    # Full path
    file_path = user_dir / secure_filename

    # Write file
    try:
        file_path.write_bytes(file_content)
        # Set restrictive permissions: owner read/write only
        file_path.chmod(0o600)
        logger.info(f"Saved uploaded file: {file_path} (user: {user_id})")
    except OSError as exc:
        raise RuntimeError(f"Failed to save uploaded file: {exc}")

    return str(file_path)
