# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Filesystem MCP Bridge
Exposes secure filesystem operations as MCP tools for LLM agents
Based on official Anthropic MCP (@modelcontextprotocol/server-filesystem)

Provides comprehensive file operations with robust security boundaries:
- Read operations (text, media, multiple files)
- Write operations (create, edit)
- Directory management (create, list, move)
- Discovery/analysis (search, tree, metadata)

Security Model:
- Whitelist-based directory access control
- Path traversal prevention
- Symlink resolution and validation
- Comprehensive audit logging
"""

import base64
import json
import logging
import mimetypes
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)
router = APIRouter(tags=["filesystem_mcp", "mcp"])

# Security Configuration: Allowed Directories
# Only paths within these directories are accessible
ALLOWED_DIRECTORIES = [
    "/home/kali/Desktop/AutoBot/",  # Project root
    "/tmp/autobot/",  # Temporary files
    "/home/kali/Desktop/",  # User workspace
]

# Maximum file size for read operations (10MB)
MAX_FILE_SIZE = 10 * 1024 * 1024


def is_path_allowed(path: str) -> bool:
    """
    Validate path is within allowed directories with security checks

    Security measures:
    - Resolves symlinks to prevent symlink attacks
    - Blocks path traversal (..)
    - Checks against whitelist of allowed directories
    """
    try:
        # Convert to absolute path
        abs_path = os.path.abspath(path)

        # Resolve symlinks to actual path
        real_path = os.path.realpath(abs_path)

        # Block path traversal attempts
        if ".." in path:
            logger.warning(f"Path traversal attempt blocked: {path}")
            return False

        # Verify resolved path matches absolute path (no symlink trickery)
        if abs_path != real_path and not real_path.startswith(tuple(ALLOWED_DIRECTORIES)):
            logger.warning(f"Symlink outside allowed directories blocked: {path} -> {real_path}")
            return False

        # Check if path is within allowed directories
        is_allowed = any(
            real_path.startswith(allowed_dir)
            for allowed_dir in ALLOWED_DIRECTORIES
        )

        if not is_allowed:
            logger.warning(f"Access denied to path outside allowed directories: {real_path}")

        return is_allowed

    except Exception as e:
        logger.error(f"Path validation error for {path}: {e}")
        return False


class MCPTool(BaseModel):
    """Standard MCP tool definition"""

    name: str
    description: str
    input_schema: Dict[str, Any]


# Request Models

class ReadTextFileRequest(BaseModel):
    """Request model for reading text files"""
    path: str = Field(..., description="Absolute path to file")
    head: Optional[int] = Field(None, description="Read only first N lines")
    tail: Optional[int] = Field(None, description="Read only last N lines")


class ReadMediaFileRequest(BaseModel):
    """Request model for reading media files (images, audio)"""
    path: str = Field(..., description="Absolute path to media file")


class ReadMultipleFilesRequest(BaseModel):
    """Request model for reading multiple files"""
    paths: List[str] = Field(..., description="List of absolute file paths")


class WriteFileRequest(BaseModel):
    """Request model for writing files"""
    path: str = Field(..., description="Absolute path to file")
    content: str = Field(..., description="File content to write")


class EditFileRequest(BaseModel):
    """Request model for editing files"""
    path: str = Field(..., description="Absolute path to file")
    edits: List[Dict[str, str]] = Field(..., description="List of {old_text, new_text} edits")
    dry_run: Optional[bool] = Field(False, description="Preview changes without applying")


class CreateDirectoryRequest(BaseModel):
    """Request model for creating directories"""
    path: str = Field(..., description="Absolute path to directory")


class ListDirectoryRequest(BaseModel):
    """Request model for listing directory contents"""
    path: str = Field(..., description="Absolute path to directory")


class ListDirectoryWithSizesRequest(BaseModel):
    """Request model for listing directory with sizes"""
    path: str = Field(..., description="Absolute path to directory")
    sort_by: Optional[str] = Field("name", description="Sort by 'name' or 'size'")


class MoveFileRequest(BaseModel):
    """Request model for moving/renaming files"""
    source: str = Field(..., description="Source path")
    destination: str = Field(..., description="Destination path")


class SearchFilesRequest(BaseModel):
    """Request model for searching files"""
    path: str = Field(..., description="Directory to search")
    pattern: str = Field(..., description="Search pattern (e.g., '*.py')")
    exclude_patterns: Optional[List[str]] = Field(None, description="Patterns to exclude")


class DirectoryTreeRequest(BaseModel):
    """Request model for directory tree"""
    path: str = Field(..., description="Root directory path")


class GetFileInfoRequest(BaseModel):
    """Request model for file metadata"""
    path: str = Field(..., description="File or directory path")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_filesystem_mcp_tools",
    error_code_prefix="FILESYSTEM_MCP",
)
@router.get("/mcp/tools")
async def get_filesystem_mcp_tools() -> List[MCPTool]:
    """Get available MCP tools for filesystem operations"""
    tools = [
        # Read Operations
        MCPTool(
            name="read_text_file",
            description="Read complete text file contents with optional head/tail parameters for large files",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to text file"},
                    "head": {"type": "integer", "description": "Read only first N lines"},
                    "tail": {"type": "integer", "description": "Read only last N lines"}
                },
                "required": ["path"]
            }
        ),
        MCPTool(
            name="read_media_file",
            description="Read media files (images, audio) as base64-encoded data with MIME type detection",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to media file"}
                },
                "required": ["path"]
            }
        ),
        MCPTool(
            name="read_multiple_files",
            description="Batch read multiple text files efficiently with graceful error handling per file",
            input_schema={
                "type": "object",
                "properties": {
                    "paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of absolute file paths to read"
                    }
                },
                "required": ["paths"]
            }
        ),

        # Write Operations
        MCPTool(
            name="write_file",
            description="Create new file or completely overwrite existing file with provided content",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to file"},
                    "content": {"type": "string", "description": "File content to write"}
                },
                "required": ["path", "content"]
            }
        ),
        MCPTool(
            name="edit_file",
            description="Selectively modify file contents using pattern-based find-and-replace edits",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to file"},
                    "edits": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "old_text": {"type": "string", "description": "Text to find"},
                                "new_text": {"type": "string", "description": "Replacement text"}
                            },
                            "required": ["old_text", "new_text"]
                        },
                        "description": "List of find-and-replace operations"
                    },
                    "dry_run": {"type": "boolean", "description": "Preview changes without applying", "default": False}
                },
                "required": ["path", "edits"]
            }
        ),

        # Directory Management
        MCPTool(
            name="create_directory",
            description="Create directory with automatic parent directory creation (recursive mkdir)",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to directory"}
                },
                "required": ["path"]
            }
        ),
        MCPTool(
            name="list_directory",
            description="List directory contents with [FILE] and [DIR] prefixes for easy identification",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to directory"}
                },
                "required": ["path"]
            }
        ),
        MCPTool(
            name="list_directory_with_sizes",
            description="List directory contents with detailed size information and sortable metrics",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to directory"},
                    "sort_by": {
                        "type": "string",
                        "enum": ["name", "size"],
                        "description": "Sort entries by name or size",
                        "default": "name"
                    }
                },
                "required": ["path"]
            }
        ),
        MCPTool(
            name="move_file",
            description="Move or rename files and directories to new location",
            input_schema={
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source file/directory path"},
                    "destination": {"type": "string", "description": "Destination path"}
                },
                "required": ["source", "destination"]
            }
        ),

        # Discovery/Analysis
        MCPTool(
            name="search_files",
            description="Recursively search for files matching glob pattern with optional exclusion patterns",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory to search in"},
                    "pattern": {"type": "string", "description": "Glob pattern (e.g., '*.py', '**/*.json')"},
                    "exclude_patterns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Patterns to exclude from results"
                    }
                },
                "required": ["path", "pattern"]
            }
        ),
        MCPTool(
            name="directory_tree",
            description="Get recursive directory structure as JSON tree with files and subdirectories",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Root directory path"}
                },
                "required": ["path"]
            }
        ),
        MCPTool(
            name="get_file_info",
            description="Get comprehensive file/directory metadata (size, timestamps, permissions, type)",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File or directory path"}
                },
                "required": ["path"]
            }
        ),
        MCPTool(
            name="list_allowed_directories",
            description="Display current filesystem access boundaries and allowed directory paths",
            input_schema={"type": "object", "properties": {}}
        ),
    ]
    return tools


# Tool Implementations

@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="read_text_file_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
@router.post("/mcp/read_text_file")
async def read_text_file_mcp(request: ReadTextFileRequest) -> Dict[str, Any]:
    """Read text file with security validation"""
    if not is_path_allowed(request.path):
        raise HTTPException(status_code=403, detail=f"Access denied: Path not in allowed directories")

    if not os.path.exists(request.path):
        raise HTTPException(status_code=404, detail=f"File not found: {request.path}")

    if not os.path.isfile(request.path):
        raise HTTPException(status_code=400, detail=f"Path is not a file: {request.path}")

    # Check file size
    file_size = os.path.getsize(request.path)
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"File too large: {file_size} bytes (max {MAX_FILE_SIZE})")

    try:
        with open(request.path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Apply head/tail filters
        if request.head is not None:
            lines = lines[:request.head]
        elif request.tail is not None:
            lines = lines[-request.tail:]

        content = ''.join(lines)

        return {
            "success": True,
            "path": request.path,
            "content": content,
            "lines": len(lines),
            "size_bytes": file_size
        }
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File is not a text file (encoding error)")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="read_media_file_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
@router.post("/mcp/read_media_file")
async def read_media_file_mcp(request: ReadMediaFileRequest) -> Dict[str, Any]:
    """Read media file as base64 with MIME type"""
    if not is_path_allowed(request.path):
        raise HTTPException(status_code=403, detail="Access denied: Path not in allowed directories")

    if not os.path.exists(request.path):
        raise HTTPException(status_code=404, detail=f"File not found: {request.path}")

    if not os.path.isfile(request.path):
        raise HTTPException(status_code=400, detail=f"Path is not a file: {request.path}")

    # Check file size
    file_size = os.path.getsize(request.path)
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"File too large: {file_size} bytes")

    # Detect MIME type
    mime_type, _ = mimetypes.guess_type(request.path)
    if mime_type is None:
        mime_type = "application/octet-stream"

    try:
        with open(request.path, 'rb') as f:
            file_data = f.read()

        base64_data = base64.b64encode(file_data).decode('utf-8')

        return {
            "success": True,
            "path": request.path,
            "mime_type": mime_type,
            "base64_data": base64_data,
            "size_bytes": file_size
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading media file: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="read_multiple_files_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
@router.post("/mcp/read_multiple_files")
async def read_multiple_files_mcp(request: ReadMultipleFilesRequest) -> Dict[str, Any]:
    """Batch read multiple files with graceful error handling"""
    results = []
    errors = []

    for path in request.paths:
        try:
            if not is_path_allowed(path):
                errors.append({"path": path, "error": "Access denied"})
                continue

            if not os.path.exists(path):
                errors.append({"path": path, "error": "File not found"})
                continue

            if not os.path.isfile(path):
                errors.append({"path": path, "error": "Not a file"})
                continue

            file_size = os.path.getsize(path)
            if file_size > MAX_FILE_SIZE:
                errors.append({"path": path, "error": f"File too large ({file_size} bytes)"})
                continue

            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            results.append({
                "path": path,
                "content": content,
                "size_bytes": file_size
            })
        except Exception as e:
            errors.append({"path": path, "error": str(e)})

    return {
        "success": True,
        "files_read": len(results),
        "files_failed": len(errors),
        "results": results,
        "errors": errors if errors else None
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="write_file_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
@router.post("/mcp/write_file")
async def write_file_mcp(request: WriteFileRequest) -> Dict[str, Any]:
    """Write file with security validation"""
    if not is_path_allowed(request.path):
        raise HTTPException(status_code=403, detail="Access denied: Path not in allowed directories")

    # Create parent directories if needed
    parent_dir = os.path.dirname(request.path)
    if parent_dir and not os.path.exists(parent_dir):
        if not is_path_allowed(parent_dir):
            raise HTTPException(status_code=403, detail="Access denied: Parent directory not allowed")
        os.makedirs(parent_dir, exist_ok=True)

    try:
        with open(request.path, 'w', encoding='utf-8') as f:
            f.write(request.content)

        file_size = os.path.getsize(request.path)

        return {
            "success": True,
            "path": request.path,
            "size_bytes": file_size,
            "message": f"File written successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error writing file: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="edit_file_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
@router.post("/mcp/edit_file")
async def edit_file_mcp(request: EditFileRequest) -> Dict[str, Any]:
    """Edit file using find-and-replace patterns"""
    if not is_path_allowed(request.path):
        raise HTTPException(status_code=403, detail="Access denied: Path not in allowed directories")

    if not os.path.exists(request.path):
        raise HTTPException(status_code=404, detail=f"File not found: {request.path}")

    if not os.path.isfile(request.path):
        raise HTTPException(status_code=400, detail=f"Path is not a file: {request.path}")

    try:
        with open(request.path, 'r', encoding='utf-8') as f:
            content = f.read()

        original_content = content
        edits_applied = []

        for edit in request.edits:
            old_text = edit.get("old_text", edit.get("oldText"))
            new_text = edit.get("new_text", edit.get("newText"))

            if old_text in content:
                content = content.replace(old_text, new_text)
                edits_applied.append({"old": old_text[:50], "new": new_text[:50]})

        # Write changes if not dry run
        if not request.dry_run:
            with open(request.path, 'w', encoding='utf-8') as f:
                f.write(content)

        return {
            "success": True,
            "path": request.path,
            "edits_applied": len(edits_applied),
            "dry_run": request.dry_run,
            "changes": edits_applied,
            "size_before": len(original_content),
            "size_after": len(content)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error editing file: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_directory_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
@router.post("/mcp/create_directory")
async def create_directory_mcp(request: CreateDirectoryRequest) -> Dict[str, Any]:
    """Create directory with recursive parent creation"""
    if not is_path_allowed(request.path):
        raise HTTPException(status_code=403, detail="Access denied: Path not in allowed directories")

    try:
        os.makedirs(request.path, exist_ok=True)

        return {
            "success": True,
            "path": request.path,
            "message": "Directory created successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating directory: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_directory_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
@router.post("/mcp/list_directory")
async def list_directory_mcp(request: ListDirectoryRequest) -> Dict[str, Any]:
    """List directory contents with type prefixes"""
    if not is_path_allowed(request.path):
        raise HTTPException(status_code=403, detail="Access denied: Path not in allowed directories")

    if not os.path.exists(request.path):
        raise HTTPException(status_code=404, detail=f"Directory not found: {request.path}")

    if not os.path.isdir(request.path):
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {request.path}")

    try:
        entries = []
        for name in os.listdir(request.path):
            full_path = os.path.join(request.path, name)
            is_dir = os.path.isdir(full_path)
            prefix = "[DIR]" if is_dir else "[FILE]"
            entries.append(f"{prefix} {name}")

        entries.sort()

        return {
            "success": True,
            "path": request.path,
            "entry_count": len(entries),
            "entries": entries
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing directory: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_directory_with_sizes_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
@router.post("/mcp/list_directory_with_sizes")
async def list_directory_with_sizes_mcp(request: ListDirectoryWithSizesRequest) -> Dict[str, Any]:
    """List directory with detailed size information"""
    if not is_path_allowed(request.path):
        raise HTTPException(status_code=403, detail="Access denied: Path not in allowed directories")

    if not os.path.exists(request.path):
        raise HTTPException(status_code=404, detail=f"Directory not found: {request.path}")

    if not os.path.isdir(request.path):
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {request.path}")

    try:
        entries = []
        for name in os.listdir(request.path):
            full_path = os.path.join(request.path, name)
            is_dir = os.path.isdir(full_path)
            size = 0 if is_dir else os.path.getsize(full_path)

            entries.append({
                "name": name,
                "type": "directory" if is_dir else "file",
                "size_bytes": size,
                "path": full_path
            })

        # Sort by requested field
        if request.sort_by == "size":
            entries.sort(key=lambda x: x["size_bytes"], reverse=True)
        else:
            entries.sort(key=lambda x: x["name"])

        return {
            "success": True,
            "path": request.path,
            "entry_count": len(entries),
            "sorted_by": request.sort_by,
            "entries": entries
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing directory: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="move_file_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
@router.post("/mcp/move_file")
async def move_file_mcp(request: MoveFileRequest) -> Dict[str, Any]:
    """Move or rename file/directory"""
    if not is_path_allowed(request.source):
        raise HTTPException(status_code=403, detail="Access denied: Source path not in allowed directories")

    if not is_path_allowed(request.destination):
        raise HTTPException(status_code=403, detail="Access denied: Destination path not in allowed directories")

    if not os.path.exists(request.source):
        raise HTTPException(status_code=404, detail=f"Source not found: {request.source}")

    if os.path.exists(request.destination):
        raise HTTPException(status_code=409, detail=f"Destination already exists: {request.destination}")

    try:
        shutil.move(request.source, request.destination)

        return {
            "success": True,
            "source": request.source,
            "destination": request.destination,
            "message": "File moved successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error moving file: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search_files_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
@router.post("/mcp/search_files")
async def search_files_mcp(request: SearchFilesRequest) -> Dict[str, Any]:
    """Search for files matching pattern"""
    if not is_path_allowed(request.path):
        raise HTTPException(status_code=403, detail="Access denied: Path not in allowed directories")

    if not os.path.exists(request.path):
        raise HTTPException(status_code=404, detail=f"Directory not found: {request.path}")

    if not os.path.isdir(request.path):
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {request.path}")

    try:
        import fnmatch

        matches = []
        exclude_patterns = request.exclude_patterns or []

        for root, dirs, files in os.walk(request.path):
            for filename in files:
                # Check if matches pattern
                if fnmatch.fnmatch(filename, request.pattern):
                    # Check if excluded
                    excluded = any(fnmatch.fnmatch(filename, pat) for pat in exclude_patterns)
                    if not excluded:
                        full_path = os.path.join(root, filename)
                        matches.append(full_path)

        return {
            "success": True,
            "search_path": request.path,
            "pattern": request.pattern,
            "matches_found": len(matches),
            "matches": matches
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error searching files: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="directory_tree_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
@router.post("/mcp/directory_tree")
async def directory_tree_mcp(request: DirectoryTreeRequest) -> Dict[str, Any]:
    """Get recursive directory tree as JSON"""
    if not is_path_allowed(request.path):
        raise HTTPException(status_code=403, detail="Access denied: Path not in allowed directories")

    if not os.path.exists(request.path):
        raise HTTPException(status_code=404, detail=f"Directory not found: {request.path}")

    if not os.path.isdir(request.path):
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {request.path}")

    def build_tree(path):
        """Recursively build directory tree"""
        tree = {
            "name": os.path.basename(path),
            "type": "directory",
            "path": path,
            "children": []
        }

        try:
            for name in sorted(os.listdir(path)):
                full_path = os.path.join(path, name)
                if os.path.isdir(full_path):
                    tree["children"].append(build_tree(full_path))
                else:
                    tree["children"].append({
                        "name": name,
                        "type": "file",
                        "path": full_path
                    })
        except PermissionError:
            tree["error"] = "Permission denied"

        return tree

    try:
        tree = build_tree(request.path)

        return {
            "success": True,
            "root_path": request.path,
            "tree": tree
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error building directory tree: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_file_info_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
@router.post("/mcp/get_file_info")
async def get_file_info_mcp(request: GetFileInfoRequest) -> Dict[str, Any]:
    """Get comprehensive file/directory metadata"""
    if not is_path_allowed(request.path):
        raise HTTPException(status_code=403, detail="Access denied: Path not in allowed directories")

    if not os.path.exists(request.path):
        raise HTTPException(status_code=404, detail=f"Path not found: {request.path}")

    try:
        stat_info = os.stat(request.path)

        info = {
            "path": request.path,
            "name": os.path.basename(request.path),
            "type": "directory" if os.path.isdir(request.path) else "file",
            "size_bytes": stat_info.st_size,
            "created": datetime.fromtimestamp(stat_info.st_ctime).isoformat(),
            "modified": datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
            "accessed": datetime.fromtimestamp(stat_info.st_atime).isoformat(),
            "permissions": oct(stat_info.st_mode)[-3:],
        }

        # Add MIME type for files
        if os.path.isfile(request.path):
            mime_type, _ = mimetypes.guess_type(request.path)
            info["mime_type"] = mime_type or "application/octet-stream"

        return {
            "success": True,
            **info
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting file info: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_allowed_directories_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
@router.get("/mcp/list_allowed_directories")
async def list_allowed_directories_mcp() -> Dict[str, Any]:
    """List all allowed directories for filesystem access"""
    return {
        "success": True,
        "allowed_directories": ALLOWED_DIRECTORIES,
        "directory_count": len(ALLOWED_DIRECTORIES),
        "security_info": {
            "path_traversal_blocked": True,
            "symlink_validation": True,
            "max_file_size_bytes": MAX_FILE_SIZE
        }
    }
