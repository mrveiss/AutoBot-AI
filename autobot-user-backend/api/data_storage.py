# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Data Storage Management API

Provides endpoints for managing the data folder:
- Storage statistics and usage
- Directory-level cleanup operations
- Conversation/transcript management
- Database file information
"""
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from auth_middleware import check_admin_permission
from utils.catalog_http_exceptions import raise_server_error
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

router = APIRouter(prefix="/data-storage", tags=["Data Storage"])
logger = logging.getLogger(__name__)

# Data directory path
DATA_DIR = Path(__file__).parent.parent.parent / "data"


class StorageCategory(BaseModel):
    """Storage category with size info."""

    name: str
    path: str
    size_bytes: int
    size_human: str
    file_count: int
    description: str
    can_cleanup: bool = True
    cleanup_type: str = "manual"


class StorageStats(BaseModel):
    """Overall storage statistics."""

    total_size_bytes: int
    total_size_human: str
    total_files: int
    total_directories: int
    categories: list[StorageCategory]
    last_cleanup: Optional[str] = None


class CleanupRequest(BaseModel):
    """Cleanup request model."""

    category: str
    older_than_days: int = 0
    dry_run: bool = True


class CleanupResult(BaseModel):
    """Cleanup operation result."""

    category: str
    files_removed: int
    bytes_freed: int
    bytes_freed_human: str
    dry_run: bool
    errors: list[str] = []


def format_size(size_bytes: int) -> str:
    """Format bytes to human readable size."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def get_dir_size(path: Path) -> tuple[int, int]:
    """Get directory size and file count."""
    total_size = 0
    file_count = 0

    if not path.exists():
        return 0, 0

    try:
        for entry in path.rglob("*"):
            if entry.is_file():
                try:
                    total_size += entry.stat().st_size
                    file_count += 1
                except (OSError, PermissionError):
                    pass
    except (OSError, PermissionError):
        pass

    return total_size, file_count


# =============================================================================
# Storage Category Definitions (Issue #665)
# =============================================================================


def _get_protected_categories() -> list[dict]:
    """
    Get protected storage categories (cannot be cleaned up).

    Issue #665: Extracted from get_storage_categories to reduce function length.
    These are critical system data stores that should not be modified.
    """
    return [
        {
            "name": "ChromaDB Vectors",
            "path": "chromadb",
            "description": "Vector embeddings database for semantic search",
        },
        {
            "name": "Knowledge Base ChromaDB",
            "path": "chromadb_kb",
            "description": "Knowledge base vector embeddings",
        },
        {
            "name": "Knowledge Files",
            "path": "knowledge",
            "description": "Knowledge base configuration files",
        },
        {
            "name": "Knowledge Base Data",
            "path": "knowledge_base",
            "description": "Knowledge base documents and embeddings",
        },
        {
            "name": "System Knowledge",
            "path": "system_knowledge",
            "description": "System procedures, workflows, and tools",
        },
        {
            "name": "Memory Storage",
            "path": "memory",
            "description": "Agent memory and context storage",
        },
        {
            "name": "MCP Tools",
            "path": "mcp_tools",
            "description": "MCP tool configurations",
        },
    ]


def _get_cleanable_categories() -> list[dict]:
    """
    Get cleanable storage categories (can be manually cleaned up).

    Issue #665: Extracted from get_storage_categories to reduce function length.
    These are user data and reports that can be safely removed.
    """
    return [
        {
            "name": "Conversation Transcripts",
            "path": "conversation_transcripts",
            "description": "Saved conversation history transcripts",
        },
        {
            "name": "Chat Sessions",
            "path": "chats",
            "description": "Chat sessions and terminal transcripts",
        },
        {
            "name": "Conversation Files",
            "path": "conversation_files",
            "description": "Files attached to conversations",
        },
        {
            "name": "Anti-Pattern Reports",
            "path": "anti_pattern_reports",
            "description": "Code anti-pattern detection reports",
        },
        {
            "name": "Reports",
            "path": "reports",
            "description": "Generated analysis reports",
        },
        {
            "name": "File Manager Root",
            "path": "file_manager_root",
            "description": "File manager sandbox root directory",
        },
        {
            "name": "Security Data",
            "path": "security",
            "description": "Security scan results and configurations",
        },
    ]


def _build_storage_category(cat_def: dict, can_cleanup: bool) -> StorageCategory:
    """
    Build a StorageCategory from a category definition.

    Issue #665: Extracted from get_storage_categories to reduce function length.

    Args:
        cat_def: Category definition dict with name, path, description
        can_cleanup: Whether this category can be cleaned up

    Returns:
        StorageCategory with computed size and file count
    """
    dir_path = DATA_DIR / cat_def["path"]
    size_bytes, file_count = get_dir_size(dir_path)

    return StorageCategory(
        name=cat_def["name"],
        path=cat_def["path"],
        size_bytes=size_bytes,
        size_human=format_size(size_bytes),
        file_count=file_count,
        description=cat_def["description"],
        can_cleanup=can_cleanup,
        cleanup_type="manual" if can_cleanup else "protected",
    )


def get_storage_categories() -> list[StorageCategory]:
    """
    Get all storage categories with their details.

    Issue #665: Refactored to use extracted helpers for category definitions.
    Categories are grouped by type (protected vs cleanable) for maintainability.
    """
    result = []

    # Add protected categories (can_cleanup=False)
    for cat_def in _get_protected_categories():
        result.append(_build_storage_category(cat_def, can_cleanup=False))

    # Add cleanable categories (can_cleanup=True)
    for cat_def in _get_cleanable_categories():
        result.append(_build_storage_category(cat_def, can_cleanup=True))

    return result


def get_database_files() -> list[dict]:
    """Get information about database files."""
    db_files = []

    for item in DATA_DIR.iterdir():
        if item.is_file() and item.suffix == ".db":
            try:
                stat = item.stat()
                db_files.append(
                    {
                        "name": item.name,
                        "size_bytes": stat.st_size,
                        "size_human": format_size(stat.st_size),
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "can_cleanup": item.name.startswith("test_"),
                    }
                )
            except (OSError, PermissionError):
                pass

    return sorted(db_files, key=lambda x: x["size_bytes"], reverse=True)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_storage_stats",
    error_code_prefix="STORAGE",
)
@router.get("/stats", response_model=StorageStats)
async def get_storage_stats():
    """Get comprehensive storage statistics."""
    try:
        categories = get_storage_categories()

        total_size = sum(c.size_bytes for c in categories)
        total_files = sum(c.file_count for c in categories)
        total_dirs = sum(1 for _ in DATA_DIR.iterdir() if _.is_dir())

        for item in DATA_DIR.iterdir():
            if item.is_file():
                try:
                    total_size += item.stat().st_size
                    total_files += 1
                except (OSError, PermissionError):
                    pass

        return StorageStats(
            total_size_bytes=total_size,
            total_size_human=format_size(total_size),
            total_files=total_files,
            total_directories=total_dirs,
            categories=categories,
        )

    except Exception as e:
        logger.error("Error getting storage stats: %s", str(e))
        raise_server_error("STORAGE_0001", f"Error getting storage stats: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_database_files",
    error_code_prefix="STORAGE",
)
@router.get("/databases")
async def get_database_files_endpoint():
    """Get information about database files in the data directory."""
    try:
        db_files = get_database_files()
        total_size = sum(f["size_bytes"] for f in db_files)

        return {
            "databases": db_files,
            "total_count": len(db_files),
            "total_size_bytes": total_size,
            "total_size_human": format_size(total_size),
        }

    except Exception as e:
        logger.error("Error getting database files: %s", str(e))
        raise_server_error("STORAGE_0002", f"Error getting database files: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_category_details",
    error_code_prefix="STORAGE",
)
@router.get("/category/{category_path}")
async def get_category_details(
    category_path: str,
    limit: int = Query(default=100, le=1000),
):
    """Get detailed information about a specific storage category."""
    try:
        dir_path = DATA_DIR / category_path

        if not dir_path.exists():
            raise HTTPException(
                status_code=404, detail=f"Category not found: {category_path}"
            )

        if not dir_path.is_dir():
            raise HTTPException(
                status_code=400, detail=f"Not a directory: {category_path}"
            )

        files = []
        for item in sorted(
            dir_path.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True
        )[:limit]:
            try:
                stat = item.stat()
                files.append(
                    {
                        "name": item.name,
                        "is_dir": item.is_dir(),
                        "size_bytes": stat.st_size if item.is_file() else 0,
                        "size_human": (
                            format_size(stat.st_size) if item.is_file() else "-"
                        ),
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    }
                )
            except (OSError, PermissionError):
                pass

        total_size, file_count = get_dir_size(dir_path)

        return {
            "category": category_path,
            "total_size_bytes": total_size,
            "total_size_human": format_size(total_size),
            "total_files": file_count,
            "files": files,
            "showing": min(limit, len(files)),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting category details: %s", str(e))
        raise_server_error("STORAGE_0003", f"Error getting category details: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cleanup_category",
    error_code_prefix="STORAGE",
)
@router.post("/cleanup", response_model=CleanupResult)
async def cleanup_category(
    request: CleanupRequest,
    _: None = Depends(check_admin_permission),
):
    """Clean up files in a storage category. Requires admin permission."""
    try:
        dir_path = DATA_DIR / request.category

        if not dir_path.exists():
            raise HTTPException(
                status_code=404, detail=f"Category not found: {request.category}"
            )

        categories = {c.path: c for c in get_storage_categories()}
        cat_info = categories.get(request.category)

        if cat_info and not cat_info.can_cleanup:
            raise HTTPException(
                status_code=403,
                detail=f"Category '{request.category}' is protected and cannot be cleaned up",
            )

        files_removed = 0
        bytes_freed = 0
        errors = []

        cutoff_time = None
        if request.older_than_days > 0:
            cutoff_time = datetime.now().timestamp() - (
                request.older_than_days * 24 * 60 * 60
            )

        for item in dir_path.rglob("*"):
            if item.is_file():
                try:
                    stat = item.stat()
                    if cutoff_time and stat.st_mtime > cutoff_time:
                        continue

                    file_size = stat.st_size
                    if not request.dry_run:
                        item.unlink()

                    files_removed += 1
                    bytes_freed += file_size

                except (OSError, PermissionError) as e:
                    errors.append(f"Error removing {item.name}: {str(e)}")

        logger.info(
            "Cleanup %s: removed %d files, freed %s (dry_run=%s)",
            request.category,
            files_removed,
            format_size(bytes_freed),
            request.dry_run,
        )

        return CleanupResult(
            category=request.category,
            files_removed=files_removed,
            bytes_freed=bytes_freed,
            bytes_freed_human=format_size(bytes_freed),
            dry_run=request.dry_run,
            errors=errors,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error during cleanup: %s", str(e))
        raise_server_error("STORAGE_0004", f"Error during cleanup: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cleanup_old_backups",
    error_code_prefix="STORAGE",
)
@router.post("/cleanup/old-backups")
async def cleanup_old_backups(
    dry_run: bool = Query(default=True),
    _: None = Depends(check_admin_permission),
):
    """Clean up old backup directories (.old, .backup suffixes)."""
    try:
        directories_found = []
        bytes_freed = 0

        for item in DATA_DIR.iterdir():
            if item.is_dir() and (
                item.name.endswith(".old") or item.name.endswith(".backup")
            ):
                size, _ = get_dir_size(item)
                directories_found.append(
                    {
                        "name": item.name,
                        "size_bytes": size,
                        "size_human": format_size(size),
                    }
                )
                bytes_freed += size

                if not dry_run:
                    shutil.rmtree(item)
                    logger.info("Removed backup directory: %s", item.name)

        return {
            "directories_found": directories_found,
            "total_count": len(directories_found),
            "bytes_freed": bytes_freed,
            "bytes_freed_human": format_size(bytes_freed),
            "dry_run": dry_run,
            "message": (
                f"Would remove {len(directories_found)} directories"
                if dry_run
                else f"Removed {len(directories_found)} directories"
            ),
        }

    except Exception as e:
        logger.error("Error cleaning up old backups: %s", str(e))
        raise_server_error("STORAGE_0005", f"Error cleaning up old backups: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_conversation",
    error_code_prefix="STORAGE",
)
@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    _: None = Depends(check_admin_permission),
):
    """Delete a specific conversation and its associated files."""
    try:
        files_deleted = []
        errors = []

        transcript_path = (
            DATA_DIR / "conversation_transcripts" / f"{conversation_id}.json"
        )
        if transcript_path.exists():
            try:
                transcript_path.unlink()
                files_deleted.append(str(transcript_path.name))
            except (OSError, PermissionError) as e:
                errors.append(f"Error deleting transcript: {str(e)}")

        chats_dir = DATA_DIR / "chats"
        for suffix in ["_chat.json", "_terminal_transcript.txt"]:
            chat_file = chats_dir / f"{conversation_id}{suffix}"
            if chat_file.exists():
                try:
                    chat_file.unlink()
                    files_deleted.append(str(chat_file.name))
                except (OSError, PermissionError) as e:
                    errors.append(f"Error deleting chat file: {str(e)}")

        if not files_deleted and not errors:
            raise HTTPException(
                status_code=404, detail=f"Conversation not found: {conversation_id}"
            )

        return {
            "conversation_id": conversation_id,
            "files_deleted": files_deleted,
            "errors": errors,
            "success": len(errors) == 0,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error deleting conversation: %s", str(e))
        raise_server_error("STORAGE_0006", f"Error deleting conversation: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_conversations_summary",
    error_code_prefix="STORAGE",
)
@router.get("/conversations/summary")
async def get_conversations_summary():
    """Get summary of stored conversations."""
    try:
        transcripts_dir = DATA_DIR / "conversation_transcripts"
        chats_dir = DATA_DIR / "chats"

        transcripts_size, transcripts_count = get_dir_size(transcripts_dir)
        chats_size, chats_count = get_dir_size(chats_dir)

        conversation_ids = set()

        if transcripts_dir.exists():
            for f in transcripts_dir.glob("*.json"):
                conversation_ids.add(f.stem)

        if chats_dir.exists():
            for f in chats_dir.glob("*_chat.json"):
                conversation_ids.add(f.stem.replace("_chat", ""))

        return {
            "unique_conversations": len(conversation_ids),
            "transcripts": {
                "count": transcripts_count,
                "size_bytes": transcripts_size,
                "size_human": format_size(transcripts_size),
            },
            "chats": {
                "count": chats_count,
                "size_bytes": chats_size,
                "size_human": format_size(chats_size),
            },
            "total_size_bytes": transcripts_size + chats_size,
            "total_size_human": format_size(transcripts_size + chats_size),
        }

    except Exception as e:
        logger.error("Error getting conversations summary: %s", str(e))
        raise_server_error(
            "STORAGE_0007", f"Error getting conversations summary: {str(e)}"
        )
