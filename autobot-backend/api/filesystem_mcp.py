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
- MCP Resources (Issue MVA-2164): Expose filesystem paths as browseable resources
- MCP Prompts (Issue MVA-2164): Predefined prompt templates for common tasks

Security Model:
- Whitelist-based directory access control
- Path traversal prevention
- Symlink resolution and validation
- Comprehensive audit logging

Issue #718: Uses dedicated thread pool for file I/O to prevent blocking
when the main asyncio thread pool is saturated by indexing operations.

MCP Resources and Prompts Architecture (Issue MVA-2164)
========================================================

Resources:
----------
MCP resources provide a standardized way to expose filesystem paths as
browseable, addressable resources using the file:// URI scheme.

Endpoints:
  - GET  /mcp/resources       - List available file resources
  - POST /mcp/resources/read  - Read a resource by URI (file:// scheme)

Resource URIs follow the pattern: file:///absolute/path/to/resource

Implementation Details:
  - Resources are generated from ALLOWED_DIRECTORIES
  - Only directories that exist are exposed as resources
  - URI-to-path conversion validates against security boundaries
  - MIME type detection for proper content handling
  - Same size limits apply as for regular file reads (MAX_FILE_SIZE)

Prompts:
--------
MCP prompt templates provide predefined, parameterized prompts for common
filesystem analysis tasks. Templates interpolate arguments to generate
contextual instructions for LLMs.

Endpoints:
  - GET  /mcp/prompts     - List available prompt templates
  - POST /mcp/prompts/get - Get a specific prompt with arguments

Available Templates:
  1. analyze_directory - Analyze directory structure and contents
     Arguments: path (required)

  2. summarize_file - Generate a summary of file contents
     Arguments: path (required), focus (optional)

  3. search_pattern - Search for files matching a pattern with context
     Arguments: directory (required), pattern (required)

Implementation Details:
  - Templates are defined in-code for type safety and validation
  - Arguments are validated at runtime before interpolation
  - Generated prompts follow the messages format (role + content)
  - Templates can be extended by adding new cases to get_prompt_mcp

Usage Example:
--------------
    # List available resources
    GET /api/filesystem/mcp/resources

    # Read a resource
    POST /api/filesystem/mcp/resources/read
    {"uri": "file:///tmp/autobot/data.json"}

    # List prompt templates
    GET /api/filesystem/mcp/prompts

    # Get a prompt template
    POST /api/filesystem/mcp/prompts/get
    {
      "name": "analyze_directory",
      "arguments": {"path": "/tmp/autobot/logs"}
    }

Future Extensions:
------------------
Other MCP bridges can follow this pattern by:
  1. Implementing GET /<bridge>/mcp/resources endpoint
  2. Implementing POST /<bridge>/mcp/resources/read endpoint
  3. Implementing GET /<bridge>/mcp/prompts endpoint
  4. Implementing POST /<bridge>/mcp/prompts/get endpoint
  5. Using appropriate URI schemes for their resource types
  6. Defining domain-specific prompt templates
"""

import asyncio
import base64
import mimetypes
import os
import shutil
from datetime import datetime
from typing import Dict, List

import aiofiles

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from services.mcp_bridge_manifest import MCPBridgeManifest
from type_defs.common import Metadata
from utils.io_executor import run_in_file_executor

MANIFEST = MCPBridgeManifest(
    name="filesystem_mcp",
    version="1.0.0",
    description="Filesystem Operations - Secure File & Directory Access",
    features=["read_files", "write_files", "directory_management", "search", "metadata"],
    endpoint="/api/filesystem/mcp/tools",
)

# Issue #514: Per-file locking to prevent concurrent write corruption
_file_locks: Dict[str, asyncio.Lock] = {}
_file_locks_lock = asyncio.Lock()


async def _get_file_lock(filepath: str) -> asyncio.Lock:
    """
    Get or create a lock for a specific file path (Issue #514).

    Uses per-file locking to allow concurrent writes to different files
    while preventing corruption from concurrent writes to the same file.

    Args:
        filepath: Absolute path to the file

    Returns:
        asyncio.Lock for the specified file
    """
    async with _file_locks_lock:
        if filepath not in _file_locks:
            _file_locks[filepath] = asyncio.Lock()
        return _file_locks[filepath]


from fastapi import APIRouter, Depends, HTTPException

from api.schemas_code import (
    CreateDirectoryRequest,
    DirectoryTreeRequest,
    EditFileRequest,
    FilesystemCreateDirectoryResponse,
    FilesystemDirectoryTreeResponse,
    FilesystemEditFileResponse,
    FilesystemFileInfoResponse,
    FilesystemListAllowedResponse,
    FilesystemListDirectoryResponse,
    FilesystemListDirectoryWithSizesResponse,
    FilesystemMoveFileResponse,
    FilesystemPromptGetResponse,
    FilesystemPromptsListResponse,
    FilesystemReadMediaResponse,
    FilesystemReadMultipleResponse,
    FilesystemReadTextResponse,
    FilesystemResourceReadResponse,
    FilesystemResourcesListResponse,
    FilesystemSearchFilesResponse,
    FilesystemWriteFileResponse,
    GetFileInfoRequest,
    GetPromptRequest,
    ListDirectoryRequest,
    ListDirectoryWithSizesRequest,
    MCPPromptTemplate,
    MCPResource,
    MCPTool,
    MoveFileRequest,
    ReadMediaFileRequest,
    ReadMultipleFilesRequest,
    ReadResourceRequest,
    ReadTextFileRequest,
    SearchFilesRequest,
    SubscribeResourceRequest,
    SubscribeResourceResponse,
    UnsubscribeResourceRequest,
    UnsubscribeResourceResponse,
    WriteFileRequest,
)
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.security.path_validator import validate_path
from utils.catalog_http_exceptions import raise_internal_error, raise_invalid_input, raise_not_found

logger = get_logger(__name__)
router = APIRouter(tags=["filesystem_mcp", "mcp"])


# Security Configuration: Allowed Directories
# Only paths within these directories are accessible
_BASE_DIR = config.base_dir
ALLOWED_DIRECTORIES = [
    f"{_BASE_DIR}/",  # Project root
    "/tmp/autobot/",  # Temporary files  # nosec B108
]

# Maximum file size for read operations (10MB)
MAX_FILE_SIZE = 10 * 1024 * 1024


def _should_include_file(filename: str, pattern: str, exclude_patterns: list) -> bool:
    """Check if a file should be included in search results. (Issue #315 - extracted)"""
    import fnmatch

    if not fnmatch.fnmatch(filename, pattern):
        return False
    return not any(fnmatch.fnmatch(filename, pat) for pat in exclude_patterns)


def is_path_allowed(path: str) -> bool:
    """
    Validate path is within allowed directories with security checks.

    Uses shared path validator (#1721) to resolve symlinks and
    verify containment within allowed directories.
    """
    try:
        validate_path(path, allowed_roots=ALLOWED_DIRECTORIES)
        return True
    except ValueError:
        logger.warning(
            "Access denied to path outside allowed directories: %s",
            path,
        )
        return False


def _validated_path(path: str) -> str:
    """Validate and return the resolved path string (#1721).

    Unlike ``is_path_allowed`` (which returns a bool), this helper
    returns the *resolved* path so that downstream ``open()`` calls
    operate on the validated canonical path rather than the raw
    user input.  This satisfies CodeQL taint tracking.

    Raises:
        HTTPException 403 when path is outside allowed directories.
    """
    try:
        return str(validate_path(path, allowed_roots=ALLOWED_DIRECTORIES))
    except ValueError:
        raise HTTPException(
            status_code=403,
            detail="Access denied: Path not in allowed directories",
        )


def _create_read_text_file_tool() -> MCPTool:
    """
    Create MCP tool definition for reading text files.

    Issue #620.
    """
    return MCPTool(
        name="read_text_file",
        description=("Read complete text file contents with optional head/tail parameters for" "large files"),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to text file"},
                "head": {"type": "integer", "description": "Read only first N lines"},
                "tail": {"type": "integer", "description": "Read only last N lines"},
            },
            "required": ["path"],
        },
    )


def _create_read_media_file_tool() -> MCPTool:
    """
    Create MCP tool definition for reading media files.

    Issue #620.
    """
    return MCPTool(
        name="read_media_file",
        description=("Read media files (images, audio) as base64-encoded data with" "MIME type detection"),
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Absolute path to media file"}},
            "required": ["path"],
        },
    )


def _create_read_multiple_files_tool() -> MCPTool:
    """
    Create MCP tool definition for batch reading multiple files.

    Issue #620.
    """
    return MCPTool(
        name="read_multiple_files",
        description=("Batch read multiple text files efficiently with graceful error handling per" "file"),
        input_schema={
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of absolute file paths to read",
                }
            },
            "required": ["paths"],
        },
    )


def _get_read_operation_tools() -> List[MCPTool]:
    """
    Get MCP tools for file read operations.

    Issue #281: Extracted from get_filesystem_mcp_tools to reduce function length
    and improve maintainability of tool definitions by category.
    Issue #620: Further refactored to use individual tool creation helpers.

    Returns:
        List of MCPTool definitions for read operations
    """
    return [
        _create_read_text_file_tool(),
        _create_read_media_file_tool(),
        _create_read_multiple_files_tool(),
    ]


def _create_write_file_tool() -> MCPTool:
    """
    Create MCP tool definition for writing files.

    Issue #620.
    """
    return MCPTool(
        name="write_file",
        description=("Create new file or completely overwrite existing file with" "provided content"),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to file"},
                "content": {"type": "string", "description": "File content to write"},
            },
            "required": ["path", "content"],
        },
    )


def _create_edit_file_tool() -> MCPTool:
    """
    Create MCP tool definition for editing files with find-and-replace.

    Issue #620.
    """
    return MCPTool(
        name="edit_file",
        description=("Selectively modify file contents using pattern-based find-and-replace" "edits"),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to file"},
                "edits": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "old_text": {
                                "type": "string",
                                "description": "Text to find",
                            },
                            "new_text": {
                                "type": "string",
                                "description": "Replacement text",
                            },
                        },
                        "required": ["old_text", "new_text"],
                    },
                    "description": "List of find-and-replace operations",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Preview changes without applying",
                    "default": False,
                },
            },
            "required": ["path", "edits"],
        },
    )


def _get_write_operation_tools() -> List[MCPTool]:
    """
    Get MCP tools for file write operations.

    Issue #281: Extracted from get_filesystem_mcp_tools to reduce function length
    and improve maintainability of tool definitions by category.
    Issue #620: Further refactored to use individual tool creation helpers.

    Returns:
        List of MCPTool definitions for write operations
    """
    return [
        _create_write_file_tool(),
        _create_edit_file_tool(),
    ]


def _create_directory_tool() -> MCPTool:
    """
    Create MCP tool definition for directory creation.

    Issue #665: Extracted from _get_directory_management_tools

    Returns:
        MCPTool for create_directory operation
    """
    return MCPTool(
        name="create_directory",
        description=("Create directory with automatic parent directory creation (recursive" "mkdir)"),
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to directory",
                }
            },
            "required": ["path"],
        },
    )


def _list_directory_tool() -> MCPTool:
    """
    Create MCP tool definition for listing directory contents.

    Issue #665: Extracted from _get_directory_management_tools

    Returns:
        MCPTool for list_directory operation
    """
    return MCPTool(
        name="list_directory",
        description=("List directory contents with [FILE] and [DIR] prefixes for" "easy identification"),
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to directory",
                }
            },
            "required": ["path"],
        },
    )


def _list_directory_with_sizes_tool() -> MCPTool:
    """
    Create MCP tool definition for listing directory with size information.

    Issue #665: Extracted from _get_directory_management_tools

    Returns:
        MCPTool for list_directory_with_sizes operation
    """
    return MCPTool(
        name="list_directory_with_sizes",
        description=("List directory contents with detailed size information and" "sortable metrics"),
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to directory",
                },
                "sort_by": {
                    "type": "string",
                    "enum": ["name", "size"],
                    "description": "Sort entries by name or size",
                    "default": "name",
                },
            },
            "required": ["path"],
        },
    )


def _get_directory_management_tools() -> List[MCPTool]:
    """
    Get MCP tools for directory management operations.

    Issue #281: Extracted from get_filesystem_mcp_tools to reduce function length
    and improve maintainability of tool definitions by category.
    Issue #665: Further refactored to extract individual tool creation helpers.

    Returns:
        List of MCPTool definitions for directory operations
    """
    return [
        _create_directory_tool(),
        _list_directory_tool(),
        _list_directory_with_sizes_tool(),
        MCPTool(
            name="move_file",
            description="Move or rename files and directories to new location",
            input_schema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "Source file/directory path",
                    },
                    "destination": {
                        "type": "string",
                        "description": "Destination path",
                    },
                },
                "required": ["source", "destination"],
            },
        ),
    ]


def _create_search_files_tool() -> MCPTool:
    """
    Create MCP tool definition for searching files by glob pattern.

    Issue #620.
    """
    return MCPTool(
        name="search_files",
        description=("Recursively search for files matching glob pattern with" "optional exclusion patterns"),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory to search in"},
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g., '*.py', '**/*.json')",
                },
                "exclude_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Patterns to exclude from results",
                },
            },
            "required": ["path", "pattern"],
        },
    )


def _create_directory_tree_tool() -> MCPTool:
    """
    Create MCP tool definition for getting recursive directory tree.

    Issue #620.
    """
    return MCPTool(
        name="directory_tree",
        description=("Get recursive directory structure as JSON tree with files and" "subdirectories"),
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Root directory path"}},
            "required": ["path"],
        },
    )


def _create_get_file_info_tool() -> MCPTool:
    """
    Create MCP tool definition for getting file/directory metadata.

    Issue #620.
    """
    return MCPTool(
        name="get_file_info",
        description=("Get comprehensive file/directory metadata (size, timestamps, permissions," "type)"),
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string", "description": "File or directory path"}},
            "required": ["path"],
        },
    )


def _create_list_allowed_directories_tool() -> MCPTool:
    """
    Create MCP tool definition for listing allowed directories.

    Issue #620.
    """
    return MCPTool(
        name="list_allowed_directories",
        description="Display current filesystem access boundaries and allowed directory paths",
        input_schema={"type": "object", "properties": {}},
    )


def _get_discovery_analysis_tools() -> List[MCPTool]:
    """
    Get MCP tools for file/directory discovery and analysis.

    Issue #281: Extracted from get_filesystem_mcp_tools to reduce function length
    and improve maintainability of tool definitions by category.
    Issue #620: Further refactored to use individual tool creation helpers.

    Returns:
        List of MCPTool definitions for discovery/analysis operations
    """
    return [
        _create_search_files_tool(),
        _create_directory_tree_tool(),
        _create_get_file_info_tool(),
        _create_list_allowed_directories_tool(),
    ]


@router.get("/mcp/tools", response_model=List[MCPTool])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_filesystem_mcp_tools",
    error_code_prefix="FILESYSTEM_MCP",
)
async def get_filesystem_mcp_tools(
    admin_check: bool = Depends(check_admin_permission),
) -> List[MCPTool]:
    """
    Get available MCP tools for filesystem operations

    Issue #744: Requires admin authentication.
    """
    # Issue #281: Use extracted helpers for tool definitions by category
    tools = []
    tools.extend(_get_read_operation_tools())
    tools.extend(_get_write_operation_tools())
    tools.extend(_get_directory_management_tools())
    tools.extend(_get_discovery_analysis_tools())
    return tools


# Tool Implementations


@router.post("/mcp/read_text_file", response_model=FilesystemReadTextResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="read_text_file_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
async def read_text_file_mcp(
    request: ReadTextFileRequest,
    admin_check: bool = Depends(check_admin_permission),
) -> Metadata:
    """
    Read text file with security validation

    Issue #744: Requires admin authentication.
    """
    safe_path = _validated_path(request.path)

    path_exists = await run_in_file_executor(os.path.exists, safe_path)
    if not path_exists:
        raise_not_found("File", request.path)

    is_file = await run_in_file_executor(os.path.isfile, safe_path)
    if not is_file:
        raise_invalid_input("path", f"not a file: {request.path}")

    # Check file size
    file_size = await run_in_file_executor(os.path.getsize, safe_path)
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {file_size} bytes (max {MAX_FILE_SIZE})",
        )

    try:
        async with aiofiles.open(safe_path, "r", encoding="utf-8") as f:  # codeql[py/path-injection]
            lines = await f.readlines()

        # Apply head/tail filters
        if request.head is not None:
            lines = lines[: request.head]
        elif request.tail is not None:
            lines = lines[-request.tail :]

        content = "".join(lines)

        return {
            "success": True,
            "path": request.path,
            "content": content,
            "lines": len(lines),
            "size_bytes": file_size,
        }
    except UnicodeDecodeError:
        raise_invalid_input("file", "not a text file (encoding error)")
    except OSError:
        raise_internal_error("Failed to read file")


@router.post("/mcp/read_media_file", response_model=FilesystemReadMediaResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="read_media_file_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
async def read_media_file_mcp(
    request: ReadMediaFileRequest,
    admin_check: bool = Depends(check_admin_permission),
) -> Metadata:
    """
    Read media file as base64 with MIME type

    Issue #744: Requires admin authentication.
    """
    safe_path = _validated_path(request.path)

    path_exists = await run_in_file_executor(os.path.exists, safe_path)
    if not path_exists:
        raise_not_found("File", request.path)

    is_file = await run_in_file_executor(os.path.isfile, safe_path)
    if not is_file:
        raise_invalid_input("path", f"not a file: {request.path}")

    # Check file size
    file_size = await run_in_file_executor(os.path.getsize, safe_path)
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"File too large: {file_size} bytes")

    # Detect MIME type
    mime_type, _ = mimetypes.guess_type(safe_path)
    if mime_type is None:
        mime_type = "application/octet-stream"

    try:
        async with aiofiles.open(safe_path, "rb") as f:  # codeql[py/path-injection]
            file_data = await f.read()

        base64_data = base64.b64encode(file_data).decode("utf-8")

        return {
            "success": True,
            "path": request.path,
            "mime_type": mime_type,
            "base64_data": base64_data,
            "size_bytes": file_size,
        }
    except OSError:
        raise_internal_error("Failed to read media file")
    except Exception:
        raise_internal_error("Error reading media file")


async def _read_single_file_for_batch(path: str) -> dict:
    """
    Read a single file for batch operation with graceful error handling.

    Issue #620: Extracted from read_multiple_files_mcp to reduce function length.

    Args:
        path: File path to read

    Returns:
        Dict with either 'result' or 'error' key
    """
    try:
        safe_path = _validated_path(path)
    except HTTPException:
        return {"error": {"path": path, "error": "Access denied"}}

    try:
        path_exists = await run_in_file_executor(os.path.exists, safe_path)
        if not path_exists:
            return {"error": {"path": path, "error": "File not found"}}

        is_file = await run_in_file_executor(os.path.isfile, safe_path)
        if not is_file:
            return {"error": {"path": path, "error": "Not a file"}}

        file_size = await run_in_file_executor(os.path.getsize, safe_path)
        if file_size > MAX_FILE_SIZE:
            return {
                "error": {
                    "path": path,
                    "error": f"File too large ({file_size} bytes)",
                }
            }

        async with aiofiles.open(safe_path, "r", encoding="utf-8") as f:  # codeql[py/path-injection]
            content = await f.read()

        return {"result": {"path": path, "content": content, "size_bytes": file_size}}
    except OSError:
        return {"error": {"path": path, "error": "Failed to read file"}}
    except Exception:
        return {"error": {"path": path, "error": "Internal server error"}}


def _separate_batch_read_results(all_results: list) -> tuple:
    """
    Separate batch read results into successes and errors.

    Issue #620: Extracted from read_multiple_files_mcp to reduce function length.

    Args:
        all_results: List of results from asyncio.gather

    Returns:
        Tuple of (results_list, errors_list)
    """
    results = []
    errors = []
    for item in all_results:
        if isinstance(item, Exception):
            errors.append({"path": "unknown", "error": str(item)})
        elif "result" in item:
            results.append(item["result"])
        elif "error" in item:
            errors.append(item["error"])
    return results, errors


@router.post("/mcp/read_multiple_files", response_model=FilesystemReadMultipleResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="read_multiple_files_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
async def read_multiple_files_mcp(
    request: ReadMultipleFilesRequest,
    admin_check: bool = Depends(check_admin_permission),
) -> Metadata:
    """
    Batch read multiple files with graceful error handling.

    Issue #744: Requires admin authentication.
    Issue #620: Refactored to use helper functions.
    """
    # Read all files in parallel - eliminates N+1 sequential I/O
    all_results = await asyncio.gather(
        *[_read_single_file_for_batch(path) for path in request.paths],
        return_exceptions=True,
    )

    # Separate results and errors using helper
    results, errors = _separate_batch_read_results(all_results)

    return {
        "success": True,
        "files_read": len(results),
        "files_failed": len(errors),
        "results": results,
        "errors": errors if errors else None,
    }


@router.post("/mcp/write_file", response_model=FilesystemWriteFileResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="write_file_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
async def write_file_mcp(
    request: WriteFileRequest,
    admin_check: bool = Depends(check_admin_permission),
) -> Metadata:
    """
    Write file with security validation

    Issue #744: Requires admin authentication.
    """
    safe_path = _validated_path(request.path)

    # Create parent directories if needed
    parent_dir = os.path.dirname(safe_path)
    parent_exists = await run_in_file_executor(os.path.exists, parent_dir) if parent_dir else True
    if parent_dir and not parent_exists:
        _validated_path(parent_dir)  # validate parent too
        await run_in_file_executor(os.makedirs, parent_dir, exist_ok=True)

    try:
        # Issue #514: Use per-file locking
        file_lock = await _get_file_lock(safe_path)
        async with file_lock:
            async with aiofiles.open(safe_path, "w", encoding="utf-8") as f:  # codeql[py/path-injection]
                await f.write(request.content)

        file_size = await run_in_file_executor(os.path.getsize, safe_path)

        return {
            "success": True,
            "path": request.path,
            "size_bytes": file_size,
            "message": "File written successfully",
        }
    except OSError:
        raise_internal_error("Failed to write file")
    except Exception:
        raise_internal_error("Error writing file")


async def _validate_file_path(path: str) -> str:
    """
    Validate that path is an allowed, existing file.

    Issue #620.  Issue #1721 - returns resolved path.

    Args:
        path: File path to validate

    Returns:
        Resolved safe path string

    Raises:
        HTTPException: If path is not allowed, doesn't exist,
        or isn't a file
    """
    safe = _validated_path(path)

    path_exists = await run_in_file_executor(os.path.exists, safe)
    if not path_exists:
        raise_not_found("File", path)

    is_file = await run_in_file_executor(os.path.isfile, safe)
    if not is_file:
        raise_invalid_input("path", f"not a file: {path}")
    return safe


def _apply_edits_to_content(content: str, edits: list) -> tuple:
    """
    Apply find-and-replace edits to content.

    Issue #620.

    Args:
        content: Original file content
        edits: List of edit dictionaries with old_text/new_text

    Returns:
        Tuple of (modified_content, list_of_applied_edits)
    """
    edits_applied = []
    for edit in edits:
        old_text = edit.get("old_text", edit.get("oldText"))
        new_text = edit.get("new_text", edit.get("newText"))

        if old_text in content:
            content = content.replace(old_text, new_text)
            edits_applied.append({"old": old_text[:50], "new": new_text[:50]})

    return content, edits_applied


@router.post("/mcp/edit_file", response_model=FilesystemEditFileResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="edit_file_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
async def edit_file_mcp(
    request: EditFileRequest,
    admin_check: bool = Depends(check_admin_permission),
) -> Metadata:
    """
    Edit file using find-and-replace patterns.

    Issue #744: Requires admin authentication.
    Issue #620: Refactored to use extracted helper methods.
    """
    safe_path = await _validate_file_path(request.path)

    try:
        # Issue #514: Use per-file locking
        file_lock = await _get_file_lock(safe_path)
        async with file_lock:
            async with aiofiles.open(safe_path, "r", encoding="utf-8") as f:  # codeql[py/path-injection]
                original_content = await f.read()

            content, edits_applied = _apply_edits_to_content(original_content, request.edits)

            if not request.dry_run:
                async with aiofiles.open(safe_path, "w", encoding="utf-8") as f:  # codeql[py/path-injection]
                    await f.write(content)

        return {
            "success": True,
            "path": request.path,
            "edits_applied": len(edits_applied),
            "dry_run": request.dry_run,
            "changes": edits_applied,
            "size_before": len(original_content),
            "size_after": len(content),
        }
    except HTTPException:
        raise
    except OSError:
        raise_internal_error("Failed to read/write file")
    except Exception:
        raise_internal_error("Error editing file")


@router.post("/mcp/create_directory", response_model=FilesystemCreateDirectoryResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_directory_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
async def create_directory_mcp(
    request: CreateDirectoryRequest,
    admin_check: bool = Depends(check_admin_permission),
) -> Metadata:
    """
    Create directory with recursive parent creation

    Issue #744: Requires admin authentication.
    """
    safe_path = _validated_path(request.path)

    try:
        await run_in_file_executor(os.makedirs, safe_path, exist_ok=True)

        return {
            "success": True,
            "path": request.path,
            "message": "Directory created successfully",
        }
    except Exception:
        raise_internal_error("Error creating directory")


@router.post("/mcp/list_directory", response_model=FilesystemListDirectoryResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_directory_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
async def list_directory_mcp(
    request: ListDirectoryRequest,
    admin_check: bool = Depends(check_admin_permission),
) -> Metadata:
    """
    List directory contents with type prefixes

    Issue #744: Requires admin authentication.
    """
    safe_path = _validated_path(request.path)

    path_exists = await run_in_file_executor(os.path.exists, safe_path)
    if not path_exists:
        raise_not_found("Directory", request.path)

    is_dir = await run_in_file_executor(os.path.isdir, safe_path)
    if not is_dir:
        raise_invalid_input("path", f"not a directory: {request.path}")

    try:
        dir_contents = await run_in_file_executor(os.listdir, safe_path)

        # Check all entries in parallel - eliminates N+1 sequential I/O
        # Issue #718: Use dedicated file I/O executor
        full_paths = [os.path.join(safe_path, name) for name in dir_contents]
        is_dir_checks = await asyncio.gather(*[run_in_file_executor(os.path.isdir, fp) for fp in full_paths])

        entries = []
        for name, entry_is_dir in zip(dir_contents, is_dir_checks):
            prefix = "[DIR]" if entry_is_dir else "[FILE]"
            entries.append(f"{prefix} {name}")

        entries.sort()

        return {
            "success": True,
            "path": request.path,
            "entry_count": len(entries),
            "entries": entries,
        }
    except Exception:
        raise_internal_error("Error listing directory")


async def _validate_directory_path(path: str) -> str:
    """
    Validate that path is an allowed, existing directory.

    Issue #620.  Issue #1721 - returns resolved safe path.

    Args:
        path: Directory path to validate

    Returns:
        Resolved safe path string

    Raises:
        HTTPException: If path is not allowed, doesn't exist,
        or isn't a directory
    """
    safe = _validated_path(path)

    path_exists = await run_in_file_executor(os.path.exists, safe)
    if not path_exists:
        raise_not_found("Directory", path)

    is_dir = await run_in_file_executor(os.path.isdir, safe)
    if not is_dir:
        raise_invalid_input("path", f"not a directory: {path}")
    return safe


async def _build_directory_entries_with_sizes(path: str) -> list:
    """
    Build directory entries with size information.

    Issue #620: Extracted from list_directory_with_sizes_mcp.
    Issue #718: Uses dedicated file I/O executor for parallel operations.

    Args:
        path: Directory path to list

    Returns:
        List of entry dictionaries with name, type, size_bytes, path
    """
    dir_contents = await run_in_file_executor(os.listdir, path)
    full_paths = [os.path.join(path, name) for name in dir_contents]

    # Batch check all entries in parallel - eliminates N+1 sequential I/O
    is_dir_checks = await asyncio.gather(*[run_in_file_executor(os.path.isdir, fp) for fp in full_paths])

    # Get sizes for files only (directories are 0)
    async def get_size_if_file(file_path: str, is_directory: bool) -> int:
        if is_directory:
            return 0
        return await run_in_file_executor(os.path.getsize, file_path)

    sizes = await asyncio.gather(*[get_size_if_file(fp, is_d) for fp, is_d in zip(full_paths, is_dir_checks)])

    entries = []
    for name, full_path, entry_is_dir, size in zip(dir_contents, full_paths, is_dir_checks, sizes):
        entries.append(
            {
                "name": name,
                "type": "directory" if entry_is_dir else "file",
                "size_bytes": size,
                "path": full_path,
            }
        )
    return entries


@router.post("/mcp/list_directory_with_sizes", response_model=FilesystemListDirectoryWithSizesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_directory_with_sizes_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
async def list_directory_with_sizes_mcp(
    request: ListDirectoryWithSizesRequest,
    admin_check: bool = Depends(check_admin_permission),
) -> Metadata:
    """
    List directory with detailed size information.

    Issue #744: Requires admin authentication.
    Issue #620: Refactored to use extracted helper methods.
    """
    # Validate path (Issue #620 / #1721: uses helper)
    safe_path = await _validate_directory_path(request.path)

    try:
        # Build entries with sizes (Issue #620: uses helper)
        entries = await _build_directory_entries_with_sizes(safe_path)

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
            "entries": entries,
        }
    except HTTPException:
        raise
    except Exception:
        raise_internal_error("Error listing directory")


@router.post("/mcp/move_file", response_model=FilesystemMoveFileResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="move_file_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
async def move_file_mcp(
    request: MoveFileRequest,
    admin_check: bool = Depends(check_admin_permission),
) -> Metadata:
    """
    Move or rename file/directory

    Issue #744: Requires admin authentication.
    """
    safe_source = _validated_path(request.source)
    safe_dest = _validated_path(request.destination)

    source_exists = await run_in_file_executor(os.path.exists, safe_source)
    if not source_exists:
        raise_not_found("Source", request.source)

    dest_exists = await run_in_file_executor(os.path.exists, safe_dest)
    if dest_exists:
        raise HTTPException(status_code=409, detail=f"Destination already exists: {request.destination}")

    try:
        await run_in_file_executor(shutil.move, safe_source, safe_dest)

        return {
            "success": True,
            "source": request.source,
            "destination": request.destination,
            "message": "File moved successfully",
        }
    except Exception:
        raise_internal_error("Error moving file")


@router.post("/mcp/search_files", response_model=FilesystemSearchFilesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search_files_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
async def search_files_mcp(
    request: SearchFilesRequest,
    admin_check: bool = Depends(check_admin_permission),
) -> Metadata:
    """
    Search for files matching pattern

    Issue #744: Requires admin authentication.
    """
    safe_path = _validated_path(request.path)

    path_exists = await run_in_file_executor(os.path.exists, safe_path)
    if not path_exists:
        raise_not_found("Directory", request.path)

    is_dir = await run_in_file_executor(os.path.isdir, safe_path)
    if not is_dir:
        raise_invalid_input("path", f"not a directory: {request.path}")

    try:
        exclude_patterns = request.exclude_patterns or []
        pattern = request.pattern

        def _search_files() -> list:
            """Blocking file search wrapped for thread executor"""
            matches = []
            for root, dirs, files in os.walk(safe_path):
                for filename in files:
                    # Check pattern + exclusions using helper (Issue #315 - reduces nesting)
                    if _should_include_file(filename, pattern, exclude_patterns):
                        matches.append(os.path.join(root, filename))
            return matches

        matches = await run_in_file_executor(_search_files)

        return {
            "success": True,
            "search_path": request.path,
            "pattern": request.pattern,
            "matches_found": len(matches),
            "matches": matches,
        }
    except Exception:
        raise_internal_error("Error searching files")


@router.post("/mcp/directory_tree", response_model=FilesystemDirectoryTreeResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="directory_tree_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
async def directory_tree_mcp(
    request: DirectoryTreeRequest,
    admin_check: bool = Depends(check_admin_permission),
) -> Metadata:
    """
    Get recursive directory tree as JSON

    Issue #744: Requires admin authentication.
    """
    safe_path = _validated_path(request.path)

    path_exists = await run_in_file_executor(os.path.exists, safe_path)
    if not path_exists:
        raise_not_found("Directory", request.path)

    is_dir = await run_in_file_executor(os.path.isdir, safe_path)
    if not is_dir:
        raise_invalid_input("path", f"not a directory: {request.path}")

    def build_tree(path):
        """Recursively build directory tree (blocking, runs in thread)"""
        tree = {
            "name": os.path.basename(path),
            "type": "directory",
            "path": path,
            "children": [],
        }

        try:
            for name in sorted(os.listdir(path)):
                full_path = os.path.join(path, name)
                if os.path.isdir(full_path):
                    tree["children"].append(build_tree(full_path))
                else:
                    tree["children"].append({"name": name, "type": "file", "path": full_path})
        except PermissionError:
            tree["error"] = "Permission denied"

        return tree

    try:
        tree = await run_in_file_executor(build_tree, safe_path)

        return {"success": True, "root_path": request.path, "tree": tree}
    except Exception:
        raise_internal_error("Error building directory tree")


@router.post("/mcp/get_file_info", response_model=FilesystemFileInfoResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_file_info_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
async def get_file_info_mcp(
    request: GetFileInfoRequest,
    admin_check: bool = Depends(check_admin_permission),
) -> Metadata:
    """
    Get comprehensive file/directory metadata

    Issue #744: Requires admin authentication.
    """
    safe_path = _validated_path(request.path)

    path_exists = await run_in_file_executor(os.path.exists, safe_path)
    if not path_exists:
        raise_not_found("Path", request.path)

    try:
        stat_info = await run_in_file_executor(os.stat, safe_path)
        is_dir = await run_in_file_executor(os.path.isdir, safe_path)
        is_file = await run_in_file_executor(os.path.isfile, safe_path)

        info = {
            "path": request.path,
            "name": os.path.basename(request.path),
            "type": "directory" if is_dir else "file",
            "size_bytes": stat_info.st_size,
            "created": datetime.fromtimestamp(stat_info.st_ctime).isoformat(),
            "modified": datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
            "accessed": datetime.fromtimestamp(stat_info.st_atime).isoformat(),
            "permissions": oct(stat_info.st_mode)[-3:],
        }

        # Add MIME type for files
        if is_file:
            mime_type, _ = mimetypes.guess_type(request.path)
            info["mime_type"] = mime_type or "application/octet-stream"

        return {"success": True, **info}
    except Exception:
        raise_internal_error("Error getting file info")


@router.get("/mcp/list_allowed_directories", response_model=FilesystemListAllowedResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_allowed_directories_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
async def list_allowed_directories_mcp(
    admin_check: bool = Depends(check_admin_permission),
) -> Metadata:
    """
    List all allowed directories for filesystem access

    Issue #744: Requires admin authentication.
    """
    return {
        "success": True,
        "allowed_directories": ALLOWED_DIRECTORIES,
        "directory_count": len(ALLOWED_DIRECTORIES),
        "security_info": {
            "path_traversal_blocked": True,
            "symlink_validation": True,
            "max_file_size_bytes": MAX_FILE_SIZE,
        },
    }


# ---------------------------------------------------------------------------
# MCP Resources and Prompts (Issue MVA-2164)
# ---------------------------------------------------------------------------


@router.get("/mcp/resources", response_model=FilesystemResourcesListResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_resources_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
async def list_resources_mcp(
    admin_check: bool = Depends(check_admin_permission),
) -> Metadata:
    """
    List available file resources as MCP resources.

    Issue MVA-2164: Exposes allowed directories as browseable resources.
    Issue #744: Requires admin authentication.

    Resources use file:// URI scheme for accessing filesystem paths.
    Each allowed directory is exposed as a resource that can be read
    via the /mcp/resources/read endpoint.
    """
    resources = []

    for allowed_dir in ALLOWED_DIRECTORIES:
        # Check if directory exists
        dir_exists = await run_in_file_executor(os.path.exists, allowed_dir)
        if dir_exists:
            is_dir = await run_in_file_executor(os.path.isdir, allowed_dir)
            if is_dir:
                # Create resource for directory
                dir_name = os.path.basename(allowed_dir.rstrip("/")) or "root"
                resources.append(
                    {
                        "uri": f"file://{allowed_dir}",
                        "name": dir_name,
                        "description": f"Directory: {allowed_dir}",
                        "mime_type": "inode/directory",
                    }
                )

    return {
        "success": True,
        "resources": resources,
        "total": len(resources),
    }


@router.post("/mcp/resources/read", response_model=FilesystemResourceReadResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="read_resource_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
async def read_resource_mcp(
    request: ReadResourceRequest,
    admin_check: bool = Depends(check_admin_permission),
) -> Metadata:
    """
    Read a resource by its URI.

    Issue MVA-2164: Implements MCP resource reading via file:// URIs.
    Issue #744: Requires admin authentication.

    Supports file:// URI scheme for accessing filesystem paths.
    The URI is converted to a filesystem path and validated against
    allowed directories before reading.
    """
    # Parse file:// URI
    if not request.uri.startswith("file://"):
        raise_invalid_input("uri", "Only file:// URIs are supported")

    # Extract path from URI
    path = request.uri[7:]  # Remove 'file://'

    # Validate path
    safe_path = _validated_path(path)

    # Check if path exists
    path_exists = await run_in_file_executor(os.path.exists, safe_path)
    if not path_exists:
        raise_not_found("Resource", request.uri)

    # Check if it's a file
    is_file = await run_in_file_executor(os.path.isfile, safe_path)
    if not is_file:
        raise_invalid_input("uri", f"Resource is not a file: {request.uri}")

    # Check file size
    file_size = await run_in_file_executor(os.path.getsize, safe_path)
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Resource too large: {file_size} bytes (max {MAX_FILE_SIZE})",
        )

    # Detect MIME type
    mime_type, _ = mimetypes.guess_type(safe_path)
    if mime_type is None:
        mime_type = "text/plain"

    try:
        async with aiofiles.open(safe_path, "r", encoding="utf-8") as f:  # codeql[py/path-injection]
            content = await f.read()

        return {
            "success": True,
            "uri": request.uri,
            "content": content,
            "mime_type": mime_type,
            "size_bytes": file_size,
        }
    except UnicodeDecodeError:
        raise_invalid_input("uri", "Resource is not a text file")
    except OSError:
        raise_internal_error("Failed to read resource")


@router.post("/mcp/resources/subscribe", response_model=SubscribeResourceResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="subscribe_resource_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
async def subscribe_resource_mcp(
    request: SubscribeResourceRequest,
    admin_check: bool = Depends(check_admin_permission),
) -> Metadata:
    """
    Subscribe to resource change notifications.

    Issue MVA-2166: Implements MCP resource subscriptions for real-time updates.
    Issue #744: Requires admin authentication.

    Clients can subscribe to file:// URIs and receive notifications when files change
    via the WebSocket live events channel. Notifications are published when:
    - File is created
    - File is modified
    - File is deleted

    The response includes a WebSocket channel name that clients should subscribe to
    via /ws/live to receive notifications.

    Args:
        request: Subscription request with URI and session_id

    Returns:
        Subscription confirmation with WebSocket channel
    """
    from services.mcp_subscription_manager import get_mcp_subscription_manager

    # Validate URI
    if not request.uri.startswith("file://"):
        raise_invalid_input("uri", "Only file:// URIs are supported for filesystem subscriptions")

    # Extract and validate path
    path = request.uri[7:]  # Remove 'file://'
    safe_path = _validated_path(path)

    # Construct canonical URI from validated path to prevent path traversal
    canonical_uri = f"file://{safe_path}"

    # Subscribe via subscription manager
    success = await get_mcp_subscription_manager().subscribe(request.session_id, canonical_uri)

    if not success:
        raise_internal_error("Failed to create subscription")

    # Generate channel name for WebSocket subscription
    import hashlib
    uri_hash = hashlib.sha256(canonical_uri.encode()).hexdigest()[:16]
    channel = f"mcp:resource:{uri_hash}"

    logger.info(
        "Created subscription: session=%s, uri=%s, channel=%s",
        request.session_id[:8],
        canonical_uri,
        channel,
    )

    return {
        "success": True,
        "uri": canonical_uri,
        "session_id": request.session_id,
        "channel": channel,
        "message": f"Subscribed to {canonical_uri}. Connect to WebSocket at /ws/live and subscribe to channel: {channel}",
    }


@router.post("/mcp/resources/unsubscribe", response_model=UnsubscribeResourceResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="unsubscribe_resource_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
async def unsubscribe_resource_mcp(
    request: UnsubscribeResourceRequest,
    admin_check: bool = Depends(check_admin_permission),
) -> Metadata:
    """
    Unsubscribe from resource change notifications.

    Issue MVA-2166: Implements MCP resource subscriptions for real-time updates.
    Issue #744: Requires admin authentication.

    Removes a subscription for a specific session and resource URI.
    If this was the last subscriber for the resource, the file watcher is stopped.

    Args:
        request: Unsubscription request with URI and session_id

    Returns:
        Unsubscription confirmation
    """
    from services.mcp_subscription_manager import get_mcp_subscription_manager

    # Validate URI
    if not request.uri.startswith("file://"):
        raise_invalid_input("uri", "Only file:// URIs are supported for filesystem subscriptions")

    # Extract and validate path
    path = request.uri[7:]  # Remove 'file://'
    safe_path = _validated_path(path)

    # Construct canonical URI from validated path
    canonical_uri = f"file://{safe_path}"

    # Unsubscribe via subscription manager
    success = await get_mcp_subscription_manager().unsubscribe(request.session_id, canonical_uri)

    if not success:
        raise_internal_error("Failed to remove subscription")

    logger.info(
        "Removed subscription: session=%s, uri=%s",
        request.session_id[:8],
        canonical_uri,
    )

    return {
        "success": True,
        "uri": canonical_uri,
        "session_id": request.session_id,
        "message": f"Unsubscribed from {canonical_uri}",
    }


@router.get("/mcp/prompts", response_model=FilesystemPromptsListResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_prompts_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
async def list_prompts_mcp(
    admin_check: bool = Depends(check_admin_permission),
) -> Metadata:
    """
    List available prompt templates.

    Issue MVA-2164: Exposes predefined prompt templates for common
    filesystem analysis tasks.
    Issue #744: Requires admin authentication.

    Templates can be invoked via the /mcp/prompts/get endpoint with
    appropriate arguments to generate contextual prompts.
    """
    prompts = [
        {
            "name": "analyze_directory",
            "description": "Analyze directory structure and contents",
            "arguments": [
                {
                    "name": "path",
                    "description": "Directory path to analyze",
                    "required": True,
                }
            ],
        },
        {
            "name": "summarize_file",
            "description": "Generate a summary of a file's contents",
            "arguments": [
                {
                    "name": "path",
                    "description": "File path to summarize",
                    "required": True,
                },
                {
                    "name": "focus",
                    "description": "Aspect to focus on (e.g., 'structure', 'security', 'performance')",
                    "required": False,
                },
            ],
        },
        {
            "name": "search_pattern",
            "description": "Search for files matching a pattern with context",
            "arguments": [
                {
                    "name": "directory",
                    "description": "Directory to search in",
                    "required": True,
                },
                {
                    "name": "pattern",
                    "description": "File pattern to search for",
                    "required": True,
                },
            ],
        },
    ]

    return {
        "success": True,
        "prompts": prompts,
        "total": len(prompts),
    }


@router.post("/mcp/prompts/get", response_model=FilesystemPromptGetResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_prompt_mcp",
    error_code_prefix="FILESYSTEM_MCP",
)
async def get_prompt_mcp(
    request: GetPromptRequest,
    admin_check: bool = Depends(check_admin_permission),
) -> Metadata:
    """
    Get a specific prompt template with arguments interpolated.

    Issue MVA-2164: Returns formatted prompt messages for common
    filesystem analysis tasks.
    Issue #744: Requires admin authentication.

    The template arguments are validated and interpolated into the
    prompt to generate contextual instructions for LLMs.
    """
    if request.name == "analyze_directory":
        path = request.arguments.get("path")
        if not path:
            raise_invalid_input("arguments", "Missing required argument: path")

        return {
            "success": True,
            "name": request.name,
            "description": "Analyze directory structure and contents",
            "messages": [
                {
                    "role": "user",
                    "content": f"Please analyze the directory at {path}. "
                    f"Provide insights on:\n"
                    f"- Directory structure and organization\n"
                    f"- File types and distributions\n"
                    f"- Potential issues or improvements\n"
                    f"- Overall code quality indicators",
                }
            ],
        }

    elif request.name == "summarize_file":
        path = request.arguments.get("path")
        if not path:
            raise_invalid_input("arguments", "Missing required argument: path")

        focus = request.arguments.get("focus", "general overview")
        return {
            "success": True,
            "name": request.name,
            "description": "Generate a summary of a file's contents",
            "messages": [
                {
                    "role": "user",
                    "content": f"Please summarize the file at {path}. "
                    f"Focus on: {focus}.\n"
                    f"Provide a concise but comprehensive summary.",
                }
            ],
        }

    elif request.name == "search_pattern":
        directory = request.arguments.get("directory")
        pattern = request.arguments.get("pattern")

        if not directory:
            raise_invalid_input("arguments", "Missing required argument: directory")
        if not pattern:
            raise_invalid_input("arguments", "Missing required argument: pattern")

        return {
            "success": True,
            "name": request.name,
            "description": "Search for files matching a pattern with context",
            "messages": [
                {
                    "role": "user",
                    "content": f"Search for files in {directory} matching pattern '{pattern}'.\n"
                    f"For each match, provide:\n"
                    f"- File location and purpose\n"
                    f"- Key contents or functionality\n"
                    f"- Relationships to other files",
                }
            ],
        }

    else:
        raise_invalid_input("name", f"Unknown prompt template: {request.name}")
