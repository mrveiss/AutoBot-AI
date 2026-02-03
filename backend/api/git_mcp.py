# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Git Operations MCP Bridge
Exposes git operations as MCP tools for LLM agents
Provides safe, read-focused git repository inspection

Provides comprehensive git capabilities:
- Repository info (status, log, diff, branches)
- File inspection (blame, show, history)
- Branch operations (list, current)
- Remote information
- Commit history analysis

Security Model:
- Repository path whitelist
- No destructive operations (no push, reset --hard, etc.)
- Command argument sanitization
- Output size limits
- Rate limiting for git operations
- Comprehensive audit logging

Issue #49 - Additional MCP Bridges (Browser, HTTP, Database, Git)
"""

import asyncio
import logging
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.type_defs.common import JSONObject, Metadata
from src.config.ssot_config import PROJECT_ROOT
from src.constants.threshold_constants import QueryDefaults
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

# Default repository path from SSOT (Issue #610 - config consolidation)
DEFAULT_REPO_PATH = str(PROJECT_ROOT)
router = APIRouter(tags=["git_mcp", "mcp"])

# Issue #380: Pre-compiled regex patterns for validators
# These are called on every git request validation
_SAFE_PATH_RE = re.compile(r"^[a-zA-Z0-9_\-./]+$")  # Safe file paths
_SHELL_METACHAR_RE = re.compile(r"[;&|`$]")  # Shell injection characters
_COMMIT_REF_RE = re.compile(r"^[a-zA-Z0-9_\-./^~]+$")  # Git commit refs
_FULL_REF_RE = re.compile(r"^[a-zA-Z0-9_\-./^~:]+$")  # Git refs with colon

# Security Configuration

# Repository whitelist - only these paths can be accessed
ALLOWED_REPOSITORIES = [
    DEFAULT_REPO_PATH,  # Main AutoBot repository (from SSOT)
]

# Git commands that are SAFE (read-only operations)
SAFE_GIT_COMMANDS = [
    "status",
    "log",
    "diff",
    "show",
    "branch",
    "remote",
    "blame",
    "ls-files",
    "rev-parse",
    "describe",
    # "config" - REMOVED: can access arbitrary files via --file/--global/--system
    "tag",
]

# Blocked git argument patterns (security layer)
BLOCKED_GIT_ARGS = [
    "--file",  # Arbitrary file access
    "--global",  # Access user home directory
    "--system",  # Access system config
    "-f",  # Short form of --file
    "--exec",  # Arbitrary command execution
    "--upload-pack",
    "--receive-pack",
]

# Git commands that are BLOCKED (destructive or dangerous)
# Issue #380: Module-level tuple for dangerous git argument patterns
_DANGEROUS_GIT_PATTERNS = (
    r"[;&|`$]",  # Shell injection
    r"\.\.(/|$)",  # Path traversal (matches ../ or .. at end)
    r"%2[eE]%2[eE]",  # URL encoded ..
    r"\\x2e\\x2e",  # Hex encoded ..
)

BLOCKED_GIT_COMMANDS = [
    "push",
    "reset",
    "rebase",
    "merge",
    "cherry-pick",
    "revert",
    "checkout",
    "switch",
    "restore",
    "clean",
    "gc",
    "prune",
    "filter-branch",
    "reflog",
    "fsck",
]

# Rate limiting
MAX_GIT_OPS_PER_MINUTE = 60
git_counter = {"count": 0, "reset_time": datetime.now(timezone.utc)}
_rate_limit_lock = asyncio.Lock()

# Output limits
MAX_OUTPUT_SIZE = 1 * 1024 * 1024  # 1 MB
MAX_LOG_ENTRIES = 100
MAX_DIFF_LINES = 5000


def _is_within_allowed_path(path: Path, allowed_path: Path) -> bool:
    """Check if path is within allowed directory (Issue #315)."""
    try:
        path.relative_to(allowed_path)
        return True
    except ValueError:
        return False


def _find_git_root(path: Path, allowed_path: Path) -> bool:
    """Find git root and verify it's within allowed path (Issue #315)."""
    # Check if path itself is a git repo
    git_dir = path / ".git"
    if git_dir.exists() and git_dir.is_dir():
        return True

    # Walk up to find git repo
    current = path
    while current != current.parent:
        if (current / ".git").exists():
            return _is_within_allowed_path(current, allowed_path)
        current = current.parent

    return False


def is_repository_allowed(repo_path: str) -> bool:
    """
    Validate repository path against whitelist

    Security measures:
    - Exact path matching
    - Prevent path traversal
    - Verify git repository exists
    - Prevent symlink attacks

    Refactored for Issue #315 - reduced nesting depth from 7 to 3
    """
    try:
        raw_path = Path(repo_path)
        path = raw_path.resolve()
    except Exception as e:
        logger.error("Repository validation error for %s: %s", repo_path, e)
        return False

    # Check against whitelist
    for allowed in ALLOWED_REPOSITORIES:
        allowed_path = Path(allowed).resolve()
        if path != allowed_path and not str(path).startswith(str(allowed_path) + "/"):
            continue

        # Security: Verify resolved path stays within allowed directory
        if not _is_within_allowed_path(path, allowed_path):
            logger.warning("Symlink escape attempt detected: %s -> %s", repo_path, path)
            continue

        # Verify it's actually a git repository (or subdirectory of one)
        if _find_git_root(path, allowed_path):
            return True

    logger.warning("Repository not in whitelist: %s", repo_path)
    return False


def sanitize_git_args(args: List[str]) -> bool:
    """
    Validate git command arguments for safety

    Security measures:
    - Block shell injection characters
    - Block dangerous flags
    - Validate argument format
    - Prevent absolute path access outside repo
    - Prevent URL-encoded path traversal
    """
    # Issue #380: use module-level constant for dangerous patterns
    for arg in args:
        # Block empty arguments
        if not arg.strip():
            logger.warning("Blocked empty git argument")
            return False

        # Check against blocked argument list
        for blocked in BLOCKED_GIT_ARGS:
            if arg == blocked or arg.startswith(blocked + "="):
                logger.warning("Blocked dangerous git argument: %s", arg)
                return False

        # Check against dangerous patterns
        for pattern in _DANGEROUS_GIT_PATTERNS:
            if re.search(pattern, arg):
                logger.warning("Blocked dangerous git argument pattern: %s", arg)
                return False

        # Block absolute paths (except for known safe patterns)
        if arg.startswith("/") and not arg.startswith("--"):
            logger.warning("Blocked absolute path argument: %s", arg)
            return False

    return True


async def check_rate_limit() -> bool:
    """
    Enforce rate limiting for git operations

    Uses asyncio.Lock for thread safety in concurrent async environments
    """

    async with _rate_limit_lock:
        now = datetime.now(timezone.utc)
        elapsed = (now - git_counter["reset_time"]).total_seconds()

        # Reset counter every minute (in-place modification for thread safety)
        if elapsed >= 60:
            git_counter["count"] = 0
            git_counter["reset_time"] = now

        if git_counter["count"] >= MAX_GIT_OPS_PER_MINUTE:
            logger.warning("Rate limit exceeded: %s git ops/min", git_counter["count"])
            return False

        git_counter["count"] += 1
        return True


def _validate_git_command(git_args: List[str]) -> None:
    """Validate git command is safe and allowed (Issue #665: extracted helper)."""
    if not git_args:
        raise HTTPException(status_code=400, detail="No git command specified")

    git_subcommand = git_args[0]

    # Check against blocked commands first
    if git_subcommand in BLOCKED_GIT_COMMANDS:
        logger.warning("Blocked dangerous git command: %s", git_subcommand)
        raise HTTPException(
            status_code=403, detail=f"Git command '{git_subcommand}' is blocked"
        )

    # Verify command is in safe list
    if git_subcommand not in SAFE_GIT_COMMANDS:
        logger.warning("Blocked unsafe git command: %s", git_subcommand)
        raise HTTPException(
            status_code=403, detail=f"Git command '{git_subcommand}' is not allowed"
        )

    # Validate ALL arguments for dangerous patterns
    if not sanitize_git_args(git_args):
        raise HTTPException(
            status_code=400, detail="Git command contains unsafe arguments"
        )


async def _run_git_process(cmd: List[str], repo_path: str, timeout: int) -> Metadata:
    """Execute git process and return result (Issue #665: extracted helper)."""
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=repo_path,
    )

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise HTTPException(
            status_code=504,
            detail=f"Git command timed out after {timeout} seconds",
        )

    # Decode output with UTF-8
    stdout_str = stdout.decode("utf-8", errors="replace")
    stderr_str = stderr.decode("utf-8", errors="replace")

    # Check output size
    if len(stdout_str) > MAX_OUTPUT_SIZE:
        stdout_str = stdout_str[:MAX_OUTPUT_SIZE] + "\n... (output truncated)"

    return {
        "success": process.returncode == 0,
        "return_code": process.returncode,
        "stdout": stdout_str,
        "stderr": stderr_str,
    }


async def execute_git_command(
    repo_path: str, git_args: List[str], timeout: int = 30
) -> Metadata:
    """
    Execute git command safely with output capture (Issue #665: uses extracted helpers).

    Security controls:
    - Repository whitelist validation
    - Argument sanitization
    - Output size limits
    - Timeout enforcement
    - Error handling
    """
    try:
        # Security: Validate git subcommand is in safe list
        _validate_git_command(git_args)

        # Build full command
        cmd = ["git", "-C", repo_path] + git_args

        # Execute with timeout
        result = await _run_git_process(cmd, repo_path, timeout)
        result["command"] = " ".join(git_args)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Git command execution error: %s", e)
        raise HTTPException(status_code=500, detail=f"Git command failed: {str(e)}")


# Pydantic Models


class MCPTool(BaseModel):
    """Standard MCP tool definition"""

    name: str
    description: str
    input_schema: JSONObject


class GitStatusRequest(BaseModel):
    """Git status request model"""

    repo_path: str = Field(
        default=DEFAULT_REPO_PATH,
        description="Repository path (must be whitelisted)",
    )
    short: Optional[bool] = Field(default=False, description="Use short format output")


class GitLogRequest(BaseModel):
    """Git log request model"""

    repo_path: str = Field(
        default=DEFAULT_REPO_PATH,
        description="Repository path",
    )
    max_count: Optional[int] = Field(
        default=QueryDefaults.DEFAULT_SEARCH_LIMIT,
        ge=1,
        le=MAX_LOG_ENTRIES,
        description=f"Maximum number of commits (1-{MAX_LOG_ENTRIES})",
    )
    oneline: Optional[bool] = Field(default=False, description="Use one-line format")
    file_path: Optional[str] = Field(
        default=None, description="Filter log to specific file"
    )

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, v):
        """Ensure file path is safe"""
        if v:
            if not _SAFE_PATH_RE.match(v):
                raise ValueError("Invalid file path format")
            if ".." in v:
                raise ValueError("Path traversal not allowed")
            if v.startswith("/"):
                raise ValueError("Absolute paths not allowed")
        return v

    @field_validator("repo_path")
    @classmethod
    def validate_repo_path(cls, v):
        """Basic validation for repository path"""
        if not v or not v.strip():
            raise ValueError("Repository path cannot be empty")
        if _SHELL_METACHAR_RE.search(v):
            raise ValueError("Invalid characters in repository path")
        return v.strip()


class GitDiffRequest(BaseModel):
    """Git diff request model"""

    repo_path: str = Field(
        default=DEFAULT_REPO_PATH,
        description="Repository path",
    )
    staged: Optional[bool] = Field(
        default=False, description="Show staged changes only"
    )
    file_path: Optional[str] = Field(default=None, description="Diff specific file")
    commit: Optional[str] = Field(
        default=None, description="Compare with specific commit"
    )

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, v):
        """Ensure file path is safe"""
        if v:
            if not _SAFE_PATH_RE.match(v):
                raise ValueError("Invalid file path format")
            if ".." in v:
                raise ValueError("Path traversal not allowed")
            if v.startswith("/"):
                raise ValueError("Absolute paths not allowed")
        return v

    @field_validator("commit")
    @classmethod
    def validate_commit_ref(cls, v):
        """Ensure commit reference is safe"""
        if v and not _COMMIT_REF_RE.match(v):
            raise ValueError("Invalid commit reference format")
        return v

    @field_validator("repo_path")
    @classmethod
    def validate_repo_path(cls, v):
        """Basic validation for repository path"""
        if not v or not v.strip():
            raise ValueError("Repository path cannot be empty")
        if _SHELL_METACHAR_RE.search(v):
            raise ValueError("Invalid characters in repository path")
        return v.strip()


class GitBranchRequest(BaseModel):
    """Git branch request model"""

    repo_path: str = Field(
        default=DEFAULT_REPO_PATH,
        description="Repository path",
    )
    all_branches: Optional[bool] = Field(
        default=False, description="Show remote branches too"
    )


class GitBlameRequest(BaseModel):
    """Git blame request model"""

    repo_path: str = Field(
        default=DEFAULT_REPO_PATH,
        description="Repository path",
    )
    file_path: str = Field(..., description="File to blame")
    line_start: Optional[int] = Field(
        default=None, ge=1, description="Starting line number"
    )
    line_end: Optional[int] = Field(
        default=None, ge=1, description="Ending line number"
    )

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, v):
        """Ensure file path is safe"""
        if not _SAFE_PATH_RE.match(v):
            raise ValueError("Invalid file path format")
        if ".." in v:
            raise ValueError("Path traversal not allowed")
        if v.startswith("/"):
            raise ValueError("Absolute paths not allowed")
        return v

    @field_validator("repo_path")
    @classmethod
    def validate_repo_path(cls, v):
        """Basic validation for repository path"""
        if not v or not v.strip():
            raise ValueError("Repository path cannot be empty")
        if _SHELL_METACHAR_RE.search(v):
            raise ValueError("Invalid characters in repository path")
        return v.strip()


class GitShowRequest(BaseModel):
    """Git show request model"""

    repo_path: str = Field(
        default=DEFAULT_REPO_PATH,
        description="Repository path",
    )
    ref: str = Field(
        default="HEAD", description="Commit or ref to show (default: HEAD)"
    )

    @field_validator("ref")
    @classmethod
    def validate_ref(cls, v):
        """Ensure ref is safe"""
        if not _FULL_REF_RE.match(v):
            raise ValueError("Invalid ref format")
        return v


# MCP Tool Definitions


def _get_git_status_tools() -> List[MCPTool]:
    """
    Get MCP tools for git status and branch information.

    Issue #281: Extracted from get_git_mcp_tools to reduce function length
    and improve maintainability of tool definitions by category.

    Returns:
        List of status-related git MCP tools
    """
    return [
        MCPTool(
            name="git_status",
            description=(
                "Get current git repository status including staged, unstaged,"
                "and untracked files. Rate limited to 60 ops/minute."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": (
                            f"Repository path (default: {DEFAULT_REPO_PATH})"
                        ),
                        "default": DEFAULT_REPO_PATH,
                    },
                    "short": {
                        "type": "boolean",
                        "description": "Use short format output",
                        "default": False,
                    },
                },
                "required": [],
            },
        ),
        MCPTool(
            name="git_branch",
            description="List all branches in the repository. Shows current branch with asterisk.",
            input_schema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Repository path",
                        "default": DEFAULT_REPO_PATH,
                    },
                    "all_branches": {
                        "type": "boolean",
                        "description": "Include remote branches",
                        "default": False,
                    },
                },
                "required": [],
            },
        ),
    ]


def _get_git_history_tools() -> List[MCPTool]:
    """
    Get MCP tools for git history operations (log, show).

    Issue #281: Extracted from get_git_mcp_tools to reduce function length
    and improve maintainability of tool definitions by category.

    Returns:
        List of history-related git MCP tools
    """
    return [
        MCPTool(
            name="git_log",
            description=(
                "Get commit history with optional filtering. Shows author, date,"
                "and message."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Repository path",
                        "default": DEFAULT_REPO_PATH,
                    },
                    "max_count": {
                        "type": "integer",
                        "description": f"Max commits to show (1-{MAX_LOG_ENTRIES})",
                        "default": 10,
                        "minimum": 1,
                        "maximum": MAX_LOG_ENTRIES,
                    },
                    "oneline": {
                        "type": "boolean",
                        "description": "Use compact one-line format",
                        "default": False,
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Filter to specific file history",
                    },
                },
                "required": [],
            },
        ),
        MCPTool(
            name="git_show",
            description="Show details of a specific commit including changes. Defaults to HEAD.",
            input_schema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Repository path",
                        "default": DEFAULT_REPO_PATH,
                    },
                    "ref": {
                        "type": "string",
                        "description": "Commit SHA or ref to show",
                        "default": "HEAD",
                    },
                },
                "required": [],
            },
        ),
    ]


def _get_git_change_tools() -> List[MCPTool]:
    """
    Get MCP tools for git change analysis operations (diff, blame).

    Issue #281: Extracted from get_git_mcp_tools to reduce function length
    and improve maintainability of tool definitions by category.

    Returns:
        List of change-analysis git MCP tools
    """
    return [
        MCPTool(
            name="git_diff",
            description=(
                "Show changes between working directory and index,"
                "or between commits. Useful for code review."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Repository path",
                        "default": DEFAULT_REPO_PATH,
                    },
                    "staged": {
                        "type": "boolean",
                        "description": "Show only staged changes",
                        "default": False,
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Diff specific file only",
                    },
                    "commit": {
                        "type": "string",
                        "description": (
                            "Compare with specific commit (e.g., HEAD~1, abc123)"
                        ),
                    },
                },
                "required": [],
            },
        ),
        MCPTool(
            name="git_blame",
            description=(
                "Show line-by-line authorship of a file. Useful for"
                "understanding code history."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Repository path",
                        "default": DEFAULT_REPO_PATH,
                    },
                    "file_path": {
                        "type": "string",
                        "description": "File to analyze",
                    },
                    "line_start": {
                        "type": "integer",
                        "description": "Starting line number",
                        "minimum": 1,
                    },
                    "line_end": {
                        "type": "integer",
                        "description": "Ending line number",
                        "minimum": 1,
                    },
                },
                "required": ["file_path"],
            },
        ),
    ]


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_git_mcp_tools",
    error_code_prefix="GIT_MCP",
)
@router.get("/mcp/tools")
async def get_git_mcp_tools() -> List[MCPTool]:
    """
    Return all available Git Operations MCP tools

    This endpoint follows the MCP specification for tool discovery.
    """
    # Issue #281: Use extracted helpers for tool definitions by category
    tools = []
    tools.extend(_get_git_status_tools())
    tools.extend(_get_git_history_tools())
    tools.extend(_get_git_change_tools())
    return tools


# Tool Implementations


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="git_status_mcp",
    error_code_prefix="GIT_MCP",
)
@router.post("/mcp/status")
async def git_status_mcp(request: GitStatusRequest) -> Metadata:
    """
    Get git repository status

    Shows staged, unstaged, and untracked files
    """
    # Security checks
    if not await check_rate_limit():
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded. Try again later."
        )

    if not is_repository_allowed(request.repo_path):
        raise HTTPException(status_code=403, detail="Repository not in whitelist")

    logger.info("Git status for %s", request.repo_path)

    # Build command
    args = ["status"]
    if request.short:
        args.append("--short")

    result = await execute_git_command(request.repo_path, args)

    return {
        "success": result["success"],
        "repository": request.repo_path,
        "output": result["stdout"],
        "errors": result["stderr"] if result["stderr"] else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="git_log_mcp",
    error_code_prefix="GIT_MCP",
)
@router.post("/mcp/log")
async def git_log_mcp(request: GitLogRequest) -> Metadata:
    """
    Get commit history

    Shows commit messages, authors, and dates
    """
    # Security checks
    if not await check_rate_limit():
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded. Try again later."
        )

    if not is_repository_allowed(request.repo_path):
        raise HTTPException(status_code=403, detail="Repository not in whitelist")

    logger.info("Git log for %s", request.repo_path)

    # Build command
    args = ["log", f"--max-count={request.max_count}"]
    if request.oneline:
        args.append("--oneline")
    else:
        args.append("--pretty=format:%H%n%an <%ae>%n%ad%n%s%n%b%n---")

    if request.file_path:
        if not sanitize_git_args([request.file_path]):
            raise HTTPException(status_code=400, detail="Invalid file path")
        args.extend(["--", request.file_path])

    result = await execute_git_command(request.repo_path, args)

    return {
        "success": result["success"],
        "repository": request.repo_path,
        "commit_count": request.max_count,
        "output": result["stdout"],
        "errors": result["stderr"] if result["stderr"] else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="git_diff_mcp",
    error_code_prefix="GIT_MCP",
)
@router.post("/mcp/diff")
async def git_diff_mcp(request: GitDiffRequest) -> Metadata:
    """
    Show git diff

    Compare working directory, staged changes, or commits
    """
    # Security checks
    if not await check_rate_limit():
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded. Try again later."
        )

    if not is_repository_allowed(request.repo_path):
        raise HTTPException(status_code=403, detail="Repository not in whitelist")

    logger.info("Git diff for %s", request.repo_path)

    # Build command
    args = ["diff"]
    if request.staged:
        args.append("--staged")
    if request.commit:
        args.append(request.commit)
    if request.file_path:
        if not sanitize_git_args([request.file_path]):
            raise HTTPException(status_code=400, detail="Invalid file path")
        args.extend(["--", request.file_path])

    result = await execute_git_command(request.repo_path, args)

    # Count diff lines
    diff_lines = result["stdout"].count("\n")
    if diff_lines > MAX_DIFF_LINES:
        logger.warning("Diff output truncated: %s lines", diff_lines)

    return {
        "success": result["success"],
        "repository": request.repo_path,
        "diff_lines": min(diff_lines, MAX_DIFF_LINES),
        "output": result["stdout"],
        "errors": result["stderr"] if result["stderr"] else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="git_branch_mcp",
    error_code_prefix="GIT_MCP",
)
@router.post("/mcp/branch")
async def git_branch_mcp(request: GitBranchRequest) -> Metadata:
    """
    List git branches

    Shows local and optionally remote branches
    """
    # Security checks
    if not await check_rate_limit():
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded. Try again later."
        )

    if not is_repository_allowed(request.repo_path):
        raise HTTPException(status_code=403, detail="Repository not in whitelist")

    logger.info("Git branch for %s", request.repo_path)

    # Build command
    args = ["branch"]
    if request.all_branches:
        args.append("-a")

    result = await execute_git_command(request.repo_path, args)

    # Parse branches
    branches = []
    current_branch = None
    for line in result["stdout"].strip().split("\n"):
        if line:
            branch = line.strip()
            if branch.startswith("* "):
                current_branch = branch[2:]
                branches.append(current_branch)
            else:
                branches.append(branch)

    return {
        "success": result["success"],
        "repository": request.repo_path,
        "current_branch": current_branch,
        "branches": branches,
        "branch_count": len(branches),
        "errors": result["stderr"] if result["stderr"] else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="git_blame_mcp",
    error_code_prefix="GIT_MCP",
)
@router.post("/mcp/blame")
async def git_blame_mcp(request: GitBlameRequest) -> Metadata:
    """
    Show git blame for a file

    Line-by-line authorship information
    """
    # Security checks
    if not await check_rate_limit():
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded. Try again later."
        )

    if not is_repository_allowed(request.repo_path):
        raise HTTPException(status_code=403, detail="Repository not in whitelist")

    if not sanitize_git_args([request.file_path]):
        raise HTTPException(status_code=400, detail="Invalid file path")

    logger.info("Git blame for %s in %s", request.file_path, request.repo_path)

    # Build command
    args = ["blame"]
    if request.line_start and request.line_end:
        args.extend(["-L", f"{request.line_start},{request.line_end}"])
    args.append(request.file_path)

    result = await execute_git_command(request.repo_path, args)

    return {
        "success": result["success"],
        "repository": request.repo_path,
        "file": request.file_path,
        "output": result["stdout"],
        "errors": result["stderr"] if result["stderr"] else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="git_show_mcp",
    error_code_prefix="GIT_MCP",
)
@router.post("/mcp/show")
async def git_show_mcp(request: GitShowRequest) -> Metadata:
    """
    Show git commit details

    Displays commit info and changes for specified ref
    """
    # Security checks
    if not await check_rate_limit():
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded. Try again later."
        )

    if not is_repository_allowed(request.repo_path):
        raise HTTPException(status_code=403, detail="Repository not in whitelist")

    logger.info("Git show %s in %s", request.ref, request.repo_path)

    # Build command
    args = ["show", request.ref]

    result = await execute_git_command(request.repo_path, args)

    return {
        "success": result["success"],
        "repository": request.repo_path,
        "ref": request.ref,
        "output": result["stdout"],
        "errors": result["stderr"] if result["stderr"] else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/mcp/info")
async def get_git_repo_info() -> Metadata:
    """
    Get information about whitelisted repositories

    Returns list of allowed repositories and their status
    """
    # Security check
    if not await check_rate_limit():
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded. Try again later."
        )

    logger.info("Getting git repository info")

    repos_info = []
    for repo_path in ALLOWED_REPOSITORIES:
        path = Path(repo_path)
        git_dir = path / ".git"

        # Issue #358 - avoid blocking
        path_exists = await asyncio.to_thread(path.exists)
        git_dir_exists = await asyncio.to_thread(git_dir.exists)
        repo_info = {
            "path": repo_path,
            "exists": path_exists,
            "is_git_repo": git_dir_exists,
        }

        # Get additional info if it's a valid repo
        if repo_info["is_git_repo"]:
            try:
                # Get current branch
                result = await execute_git_command(
                    repo_path, ["rev-parse", "--abbrev-ref", "HEAD"]
                )
                repo_info["current_branch"] = result["stdout"].strip()

                # Get last commit
                result = await execute_git_command(
                    repo_path, ["log", "-1", "--oneline"]
                )
                repo_info["last_commit"] = result["stdout"].strip()

            except Exception as e:
                logger.error("Error getting repo info: %s", e)
                repo_info["error"] = str(e)

        repos_info.append(repo_info)

    return {
        "success": True,
        "repositories": repos_info,
        "repository_count": len(repos_info),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_git_mcp_status",
    error_code_prefix="GIT_MCP",
)
@router.get("/mcp/service_status")
async def get_git_mcp_status() -> Metadata:
    """
    Get Git MCP service status

    Returns:
    - Service health
    - Rate limit status
    - Configuration info
    """

    async with _rate_limit_lock:
        current_rate = git_counter["count"]
        time_until_reset = max(
            0,
            60
            - (datetime.now(timezone.utc) - git_counter["reset_time"]).total_seconds(),
        )

    return {
        "status": "operational",
        "service": "git_mcp",
        "rate_limit": {
            "current": current_rate,
            "max": MAX_GIT_OPS_PER_MINUTE,
            "reset_in_seconds": round(time_until_reset, 1),
        },
        "configuration": {
            "allowed_repositories": len(ALLOWED_REPOSITORIES),
            "safe_commands": len(SAFE_GIT_COMMANDS),
            "blocked_commands": len(BLOCKED_GIT_COMMANDS),
            "max_output_size_mb": MAX_OUTPUT_SIZE / (1024 * 1024),
            "max_log_entries": MAX_LOG_ENTRIES,
            "max_diff_lines": MAX_DIFF_LINES,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
