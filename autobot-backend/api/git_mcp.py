# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
import re
import subprocess
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from api.schemas_code import (
    GitBlameRequest,
    GitBranchRequest,
    GitDiffRequest,
    GitLogRequest,
    GitMCPInfoResponse,
    GitMCPOperationResponse,
    GitMCPServiceStatusResponse,
    GitShowRequest,
    GitStatusRequest,
    MCPTool,
    SubscribeResourceRequest,
    UnsubscribeResourceRequest,
)
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.security.path_validator import validate_path
from autobot_shared.ssot_config import PROJECT_ROOT
from autobot_shared.time_utils import now_utc
from services.mcp_bridge_manifest import MCPBridgeManifest
from services.tool_output_filter import get_tool_output_filter
from type_defs.common import Metadata

MANIFEST = MCPBridgeManifest(
    name="git_mcp",
    version="1.0.0",
    description="Git Operations - Version Control Repository Management",
    features=["status", "log", "diff", "branch", "blame", "show", "repository_whitelist"],
    endpoint="/api/git/mcp/tools",
)

logger = get_logger(__name__)

# Default repository path from SSOT (Issue #610 - config consolidation)
DEFAULT_REPO_PATH = str(PROJECT_ROOT)
router = APIRouter(
    tags=["git_mcp", "mcp"],
    dependencies=[Depends(check_admin_permission)],
)

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
git_counter = {"count": 0, "reset_time": now_utc()}
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
    Validate repository path against whitelist.

    Uses shared path validator (#1721) then verifies git root.
    """
    try:
        path = validate_path(repo_path, allowed_roots=ALLOWED_REPOSITORIES)
    except ValueError:
        logger.warning("Repository not in whitelist: %s", repo_path)
        return False

    # Verify it's actually a git repository
    for allowed in ALLOWED_REPOSITORIES:
        allowed_path = Path(allowed).resolve()
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
        now = now_utc()
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
        raise HTTPException(status_code=403, detail=f"Git command '{git_subcommand}' is blocked")

    # Verify command is in safe list
    if git_subcommand not in SAFE_GIT_COMMANDS:
        logger.warning("Blocked unsafe git command: %s", git_subcommand)
        raise HTTPException(status_code=403, detail=f"Git command '{git_subcommand}' is not allowed")

    # Validate ALL arguments for dangerous patterns
    if not sanitize_git_args(git_args):
        raise HTTPException(status_code=400, detail="Git command contains unsafe arguments")


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

    # Check output size, then apply semantic filter
    if len(stdout_str) > MAX_OUTPUT_SIZE:
        stdout_str = stdout_str[:MAX_OUTPUT_SIZE]
    stdout_str = get_tool_output_filter().prepare_and_filter(
        " ".join(cmd[:3]), stdout_str, exit_code=process.returncode
    )

    return {
        "success": process.returncode == 0,
        "return_code": process.returncode,
        "stdout": stdout_str,
        "stderr": stderr_str,
    }


async def execute_git_command(repo_path: str, git_args: List[str], timeout: int = 30) -> Metadata:
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
        raise HTTPException(status_code=500, detail="Git command failed")


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
                        "description": (f"Repository path (default: {DEFAULT_REPO_PATH})"),
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
    """Get MCP tools for git history operations (log, show). Ref: #1088."""
    return [
        MCPTool(
            name="git_log",
            description=("Get commit history with optional filtering. Shows author, date," "and message."),
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


def _make_git_blame_tool() -> MCPTool:
    """Helper for _get_git_change_tools. Ref: #1088."""
    return MCPTool(
        name="git_blame",
        description=("Show line-by-line authorship of a file. Useful for" "understanding code history."),
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
    )


def _get_git_change_tools() -> List[MCPTool]:
    """Get MCP tools for git change analysis operations (diff, blame). Ref: #1088."""
    return [
        MCPTool(
            name="git_diff",
            description=(
                "Show changes between working directory and index," "or between commits. Useful for code review."
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
                        "description": ("Compare with specific commit (e.g., HEAD~1, abc123)"),
                    },
                },
                "required": [],
            },
        ),
        _make_git_blame_tool(),
    ]


@router.get("/mcp/tools", response_model=List[MCPTool])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_git_mcp_tools",
    error_code_prefix="GIT_MCP",
)
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


@router.post("/mcp/status", response_model=GitMCPOperationResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="git_status_mcp",
    error_code_prefix="GIT_MCP",
)
async def git_status_mcp(request: GitStatusRequest) -> Metadata:
    """
    Get git repository status

    Shows staged, unstaged, and untracked files
    """
    # Security checks
    if not await check_rate_limit():
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")

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
        "timestamp": now_utc().isoformat(),
    }


@router.post("/mcp/log", response_model=GitMCPOperationResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="git_log_mcp",
    error_code_prefix="GIT_MCP",
)
async def git_log_mcp(request: GitLogRequest) -> Metadata:
    """
    Get commit history

    Shows commit messages, authors, and dates
    """
    # Security checks
    if not await check_rate_limit():
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")

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
        "timestamp": now_utc().isoformat(),
    }


@router.post("/mcp/diff", response_model=GitMCPOperationResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="git_diff_mcp",
    error_code_prefix="GIT_MCP",
)
async def git_diff_mcp(request: GitDiffRequest) -> Metadata:
    """
    Show git diff

    Compare working directory, staged changes, or commits
    """
    # Security checks
    if not await check_rate_limit():
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")

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
        "timestamp": now_utc().isoformat(),
    }


@router.post("/mcp/branch", response_model=GitMCPOperationResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="git_branch_mcp",
    error_code_prefix="GIT_MCP",
)
async def git_branch_mcp(request: GitBranchRequest) -> Metadata:
    """
    List git branches

    Shows local and optionally remote branches
    """
    # Security checks
    if not await check_rate_limit():
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")

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
        "timestamp": now_utc().isoformat(),
    }


@router.post("/mcp/blame", response_model=GitMCPOperationResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="git_blame_mcp",
    error_code_prefix="GIT_MCP",
)
async def git_blame_mcp(request: GitBlameRequest) -> Metadata:
    """
    Show git blame for a file

    Line-by-line authorship information
    """
    # Security checks
    if not await check_rate_limit():
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")

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
        "timestamp": now_utc().isoformat(),
    }


@router.post("/mcp/show", response_model=GitMCPOperationResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="git_show_mcp",
    error_code_prefix="GIT_MCP",
)
async def git_show_mcp(request: GitShowRequest) -> Metadata:
    """
    Show git commit details

    Displays commit info and changes for specified ref
    """
    # Security checks
    if not await check_rate_limit():
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")

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
        "timestamp": now_utc().isoformat(),
    }


@router.get("/mcp/info", response_model=GitMCPInfoResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_git_repo_info",
    error_code_prefix="GIT_MCP",
)
async def get_git_repo_info() -> Metadata:
    """
    Get information about whitelisted repositories

    Returns list of allowed repositories and their status
    """
    # Security check
    if not await check_rate_limit():
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")

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
                result = await execute_git_command(repo_path, ["rev-parse", "--abbrev-ref", "HEAD"])
                repo_info["current_branch"] = result["stdout"].strip()

                # Get last commit
                result = await execute_git_command(repo_path, ["log", "-1", "--oneline"])
                repo_info["last_commit"] = result["stdout"].strip()

            except Exception as e:
                logger.error("Error getting repo info: %s", e)
                repo_info["error"] = str(e)

        repos_info.append(repo_info)

    return {
        "success": True,
        "repositories": repos_info,
        "repository_count": len(repos_info),
        "timestamp": now_utc().isoformat(),
    }


@router.get("/mcp/service_status", response_model=GitMCPServiceStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_git_mcp_status",
    error_code_prefix="GIT_MCP",
)
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
            60 - (now_utc() - git_counter["reset_time"]).total_seconds(),
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
        "timestamp": now_utc().isoformat(),
    }


# ---------------------------------------------------------------------------
# MCP Resources and Prompts (Issue MVA-2165)
# ---------------------------------------------------------------------------


@router.get("/mcp/resources")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_git_resources",
    error_code_prefix="GIT_MCP",
)
async def list_git_resources() -> Metadata:
    """
    List available git resources as MCP resources.

    Issue MVA-2165: Exposes git commits, branches, and diffs as browseable resources.

    Resources use git:// URI scheme:
    - git://repo/commit/<SHA> - specific commit
    - git://repo/branch/<name> - branch tip commit
    - git://repo/diff/<base>..<head> - diff between commits
    """
    if not await check_rate_limit():
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    resources = []

    # Get repository info
    repo_path = DEFAULT_REPO_PATH
    if is_repository_allowed(repo_path):
        # Recent commits as resources
        result = await execute_git_command(repo_path, ["log", "--oneline", "--max-count=10"])
        if result["success"]:
            for line in result["stdout"].strip().split("\n"):
                if line:
                    parts = line.split(" ", 1)
                    if len(parts) == 2:
                        sha, message = parts
                        resources.append(
                            {
                                "uri": f"git://{repo_path}/commit/{sha}",
                                "name": f"Commit {sha[:7]}",
                                "description": message,
                                "mime_type": "text/x-git-commit",
                            }
                        )

        # Branches as resources
        result = await execute_git_command(repo_path, ["branch", "-a"])
        if result["success"]:
            for line in result["stdout"].strip().split("\n"):
                if line:
                    branch = line.strip().lstrip("* ").strip()
                    if branch and not branch.startswith("remotes/"):
                        resources.append(
                            {
                                "uri": f"git://{repo_path}/branch/{branch}",
                                "name": f"Branch: {branch}",
                                "description": f"Branch {branch} tip commit",
                                "mime_type": "text/x-git-branch",
                            }
                        )

    return {
        "success": True,
        "resources": resources,
        "total": len(resources),
    }


@router.post("/mcp/resources/read")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="read_git_resource",
    error_code_prefix="GIT_MCP",
)
async def read_git_resource(request: Metadata) -> Metadata:
    """
    Read a git resource by its URI.

    Issue MVA-2165: Implements MCP resource reading via git:// URIs.

    Supports:
    - git://repo/commit/<SHA> - show commit details
    - git://repo/branch/<name> - show branch tip commit
    - git://repo/diff/<base>..<head> - show diff between commits
    """
    if not await check_rate_limit():
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    uri = request.get("uri", "")
    if not uri.startswith("git://"):
        raise HTTPException(status_code=400, detail="Only git:// URIs are supported")

    # Parse URI: git://repo/type/identifier
    parts = uri[6:].split("/", 2)  # Remove 'git://'
    if len(parts) < 3:
        raise HTTPException(status_code=400, detail="Invalid git:// URI format")

    repo_path, resource_type, identifier = parts

    if not is_repository_allowed(repo_path):
        raise HTTPException(status_code=403, detail="Repository not in whitelist")

    try:
        if resource_type == "commit":
            # Show commit details
            if not _COMMIT_REF_RE.match(identifier):
                raise HTTPException(status_code=400, detail="Invalid commit reference")
            result = await execute_git_command(repo_path, ["show", identifier])
            content = result["stdout"]
            mime_type = "text/x-git-commit"

        elif resource_type == "branch":
            # Show branch tip commit
            if not sanitize_git_args([identifier]):
                raise HTTPException(status_code=400, detail="Invalid branch name")
            result = await execute_git_command(repo_path, ["show", identifier])
            content = result["stdout"]
            mime_type = "text/x-git-branch"

        elif resource_type == "diff":
            # Show diff between commits
            if ".." in identifier:
                base, head = identifier.split("..", 1)
                if not _COMMIT_REF_RE.match(base) or not _COMMIT_REF_RE.match(head):
                    raise HTTPException(status_code=400, detail="Invalid diff reference")
                result = await execute_git_command(repo_path, ["diff", f"{base}..{head}"])
            else:
                raise HTTPException(status_code=400, detail="Diff URI must use base..head format")
            content = result["stdout"]
            mime_type = "text/x-git-diff"

        else:
            raise HTTPException(status_code=400, detail=f"Unknown resource type: {resource_type}")

        if not result["success"]:
            raise HTTPException(status_code=500, detail="Git command failed")

        return {
            "success": True,
            "uri": uri,
            "content": content,
            "mime_type": mime_type,
            "size_bytes": len(content),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error reading git resource: %s", e)
        raise HTTPException(status_code=500, detail="Failed to read git resource")


@router.post("/mcp/resources/subscribe")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="subscribe_git_resource",
    error_code_prefix="GIT_MCP",
)
async def subscribe_git_resource(
    request: SubscribeResourceRequest,
    admin_check: bool = Depends(check_admin_permission),
) -> Metadata:
    """
    Subscribe to git resource change notifications.

    Issue MVA-2166: Implements MCP resource subscriptions for real-time updates.

    Clients can subscribe to git:// URIs and receive notifications when:
    - Commits are pushed
    - Branches are updated
    - Tags are created

    Note: Active change detection for git repositories will be implemented in a follow-up.
    For now, subscriptions are registered but notifications must be manually triggered
    via the MCPSubscriptionManager.publish_change() method.

    Args:
        request: Subscription request with URI and session_id

    Returns:
        Subscription confirmation with WebSocket channel
    """
    from services.mcp_subscription_manager import get_mcp_subscription_manager

    # Validate URI
    if not request.uri.startswith("git://"):
        raise HTTPException(status_code=400, detail="Only git:// URIs are supported for git subscriptions")

    # Parse URI to validate format
    parts = request.uri[6:].split("/", 2)  # Remove 'git://'
    if len(parts) < 3:
        raise HTTPException(status_code=400, detail="Invalid git:// URI format. Expected: git://repo/type/identifier")

    repo_path, resource_type, identifier = parts

    if not is_repository_allowed(repo_path):
        raise HTTPException(status_code=403, detail="Repository not in whitelist")

    if resource_type not in ["commit", "branch", "diff"]:
        raise HTTPException(status_code=400, detail=f"Unknown resource type: {resource_type}")

    # Subscribe via subscription manager
    success = await get_mcp_subscription_manager().subscribe(request.session_id, request.uri)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to create subscription")

    # Generate channel name for WebSocket subscription
    import hashlib

    uri_hash = hashlib.sha256(request.uri.encode()).hexdigest()[:16]
    channel = f"mcp:resource:{uri_hash}"

    logger.info(
        "Created git subscription: session=%s, uri=%s, channel=%s",
        request.session_id[:8],
        request.uri,
        channel,
    )

    return {
        "success": True,
        "uri": request.uri,
        "session_id": request.session_id,
        "channel": channel,
        "message": f"Subscribed to {request.uri}. Connect to WebSocket at /ws/live and subscribe to channel: {channel}",
    }


@router.post("/mcp/resources/unsubscribe")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="unsubscribe_git_resource",
    error_code_prefix="GIT_MCP",
)
async def unsubscribe_git_resource(
    request: UnsubscribeResourceRequest,
    admin_check: bool = Depends(check_admin_permission),
) -> Metadata:
    """
    Unsubscribe from git resource change notifications.

    Issue MVA-2166: Implements MCP resource subscriptions for real-time updates.

    Removes a subscription for a specific session and resource URI.

    Args:
        request: Unsubscription request with URI and session_id

    Returns:
        Unsubscription confirmation
    """
    from services.mcp_subscription_manager import get_mcp_subscription_manager

    # Validate URI
    if not request.uri.startswith("git://"):
        raise HTTPException(status_code=400, detail="Only git:// URIs are supported for git subscriptions")

    # Unsubscribe via subscription manager
    success = await get_mcp_subscription_manager().unsubscribe(request.session_id, request.uri)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to remove subscription")

    logger.info(
        "Removed git subscription: session=%s, uri=%s",
        request.session_id[:8],
        request.uri,
    )

    return {
        "success": True,
        "uri": request.uri,
        "session_id": request.session_id,
        "message": f"Unsubscribed from {request.uri}",
    }


@router.get("/mcp/prompts")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_git_prompts",
    error_code_prefix="GIT_MCP",
)
async def list_git_prompts() -> Metadata:
    """
    List available git prompt templates.

    Issue MVA-2165: Exposes predefined prompt templates for common
    git analysis tasks.

    Templates can be invoked via the /mcp/prompts/get endpoint with
    appropriate arguments to generate contextual prompts.
    """
    prompts = [
        {
            "name": "review_pr",
            "description": "Review a pull request or commit range for quality and issues",
            "arguments": [
                {
                    "name": "base",
                    "description": "Base commit or branch",
                    "required": True,
                },
                {
                    "name": "head",
                    "description": "Head commit or branch",
                    "required": True,
                },
            ],
        },
        {
            "name": "explain_commit",
            "description": "Explain what a commit does and why",
            "arguments": [
                {
                    "name": "commit",
                    "description": "Commit SHA or reference",
                    "required": True,
                },
            ],
        },
        {
            "name": "diff_analysis",
            "description": "Analyze a diff for breaking changes and impact",
            "arguments": [
                {
                    "name": "diff_ref",
                    "description": "Diff reference (e.g., HEAD~1..HEAD)",
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


@router.post("/mcp/prompts/get")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_git_prompt",
    error_code_prefix="GIT_MCP",
)
async def get_git_prompt(request: Metadata) -> Metadata:
    """
    Get a specific git prompt template with arguments interpolated.

    Issue MVA-2165: Returns formatted prompt messages for common
    git analysis tasks.

    The template arguments are validated and interpolated into the
    prompt to generate contextual instructions for LLMs.
    """
    name = request.get("name", "")
    arguments = request.get("arguments", {})

    if name == "review_pr":
        base = arguments.get("base")
        head = arguments.get("head")
        if not base or not head:
            raise HTTPException(status_code=400, detail="Missing required arguments: base, head")

        return {
            "success": True,
            "name": name,
            "description": "Review a pull request or commit range",
            "messages": [
                {
                    "role": "user",
                    "content": f"Please review the changes from {base} to {head}. "
                    f"Analyze for:\n"
                    f"- Code quality and maintainability\n"
                    f"- Potential bugs or issues\n"
                    f"- Security vulnerabilities\n"
                    f"- Breaking changes\n"
                    f"- Test coverage gaps",
                }
            ],
        }

    elif name == "explain_commit":
        commit = arguments.get("commit")
        if not commit:
            raise HTTPException(status_code=400, detail="Missing required argument: commit")

        return {
            "success": True,
            "name": name,
            "description": "Explain what a commit does",
            "messages": [
                {
                    "role": "user",
                    "content": f"Please explain commit {commit}:\n"
                    f"- What changes were made?\n"
                    f"- Why were these changes necessary?\n"
                    f"- What is the impact of these changes?\n"
                    f"- Are there any side effects to be aware of?",
                }
            ],
        }

    elif name == "diff_analysis":
        diff_ref = arguments.get("diff_ref")
        if not diff_ref:
            raise HTTPException(status_code=400, detail="Missing required argument: diff_ref")

        return {
            "success": True,
            "name": name,
            "description": "Analyze a diff for impact",
            "messages": [
                {
                    "role": "user",
                    "content": f"Please analyze the diff {diff_ref}:\n"
                    f"- Identify breaking changes\n"
                    f"- Assess backward compatibility impact\n"
                    f"- Find potential runtime issues\n"
                    f"- Evaluate performance implications\n"
                    f"- Check for missing tests or documentation",
                }
            ],
        }

    else:
        raise HTTPException(status_code=400, detail=f"Unknown prompt template: {name}")
