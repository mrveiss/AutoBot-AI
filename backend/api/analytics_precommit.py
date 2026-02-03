# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Git Pre-commit Hook Analyzer API

Issue #223: Implements git hooks that check for patterns before allowing commits.
Features fast pattern checking, clear error messages, and bypass mechanism.
"""

import asyncio
import logging
import re
import subprocess  # nosec B404
import threading
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.auth_middleware import check_admin_permission
from src.constants.network_constants import NetworkConstants

logger = logging.getLogger(__name__)

router = APIRouter(tags=["precommit", "analytics"])  # Prefix set in router_registry

# Issue #380: Module-level frozenset for expensive checks to skip in fast mode
_EXPENSIVE_CHECKS = frozenset({"QUA002", "DOC001"})


# ============================================================================
# Models
# ============================================================================


class CheckSeverity(str, Enum):
    """Severity levels for pre-commit checks."""

    BLOCK = "block"  # Prevents commit
    WARN = "warn"  # Shows warning but allows commit
    INFO = "info"  # Informational only


class CheckCategory(str, Enum):
    """Categories of pre-commit checks."""

    SECURITY = "security"
    QUALITY = "quality"
    STYLE = "style"
    DEBUG = "debug"
    DOCS = "docs"


class CheckResult(BaseModel):
    """Result of a single check."""

    check_id: str
    name: str
    category: CheckCategory
    severity: CheckSeverity
    passed: bool
    message: str
    file: Optional[str] = None
    line: Optional[int] = None
    snippet: Optional[str] = None
    suggestion: Optional[str] = None


class CommitCheckResult(BaseModel):
    """Result of checking staged files."""

    passed: bool
    total_checks: int
    passed_checks: int
    failed_checks: int
    warnings: int
    blocked: bool
    duration_ms: float
    results: list[CheckResult]
    files_checked: list[str]
    timestamp: str


class HookConfig(BaseModel):
    """Configuration for pre-commit hooks."""

    enabled: bool = True
    fast_mode: bool = True  # Skip expensive checks
    timeout_seconds: int = Field(default=5, ge=1, le=30)
    bypass_keyword: str = "[skip-hooks]"
    enabled_checks: list[str] = Field(default_factory=list)
    disabled_checks: list[str] = Field(default_factory=list)


class CheckDefinition(BaseModel):
    """Definition of a check rule."""

    id: str
    name: str
    category: CheckCategory
    severity: CheckSeverity
    pattern: str
    description: str
    suggestion: str
    file_patterns: list[str] = Field(default_factory=lambda: ["*"])
    enabled: bool = True


class HookStatus(BaseModel):
    """Status of installed hooks."""

    installed: bool
    path: Optional[str] = None
    version: Optional[str] = None
    last_run: Optional[str] = None
    config: HookConfig


# ============================================================================
# Check Definitions
# ============================================================================

BUILTIN_CHECKS: dict[str, CheckDefinition] = {
    # Security Checks
    "SEC001": CheckDefinition(
        id="SEC001",
        name="Hardcoded Password",
        category=CheckCategory.SECURITY,
        severity=CheckSeverity.BLOCK,
        pattern=r'(?i)(password|passwd|pwd)\s*[=:]\s*["\'][^"\']{4,}["\']',
        description="Detected hardcoded password",
        suggestion="Use environment variables or secrets manager",
        file_patterns=["*.py", "*.js", "*.ts", "*.json", "*.yaml", "*.yml"],
    ),
    "SEC002": CheckDefinition(
        id="SEC002",
        name="API Key Exposure",
        category=CheckCategory.SECURITY,
        severity=CheckSeverity.BLOCK,
        pattern=r'(?i)(api[_-]?key|apikey|secret[_-]?key)\s*[=:]\s*["\'][a-zA-Z0-9]{16,}["\']',
        description="Detected exposed API key",
        suggestion="Store API keys in environment variables",
        file_patterns=["*.py", "*.js", "*.ts", "*.json", "*.env"],
    ),
    "SEC003": CheckDefinition(
        id="SEC003",
        name="Private Key in Code",
        category=CheckCategory.SECURITY,
        severity=CheckSeverity.BLOCK,
        pattern=r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----",
        description="Private key detected in source file",
        suggestion="Never commit private keys - use key management service",
        file_patterns=["*"],
    ),
    "SEC004": CheckDefinition(
        id="SEC004",
        name="Hardcoded IP Address",
        category=CheckCategory.SECURITY,
        severity=CheckSeverity.WARN,
        pattern=r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b(?!.*(?:0\.0\.0\.0|127\.0\.0\.1|localhost))",  # noqa: E501
        description="Hardcoded IP address detected",
        suggestion="Use configuration or environment variables for IP addresses",
        file_patterns=["*.py", "*.js", "*.ts"],
    ),
    # Debug Checks
    "DBG001": CheckDefinition(
        id="DBG001",
        name="Console.log Statement",
        category=CheckCategory.DEBUG,
        severity=CheckSeverity.WARN,
        pattern=r"console\.(log|debug|info|warn)\s*\(",
        description="Console statement found",
        suggestion="Remove console statements before committing",
        file_patterns=["*.js", "*.ts", "*.vue"],
    ),
    "DBG002": CheckDefinition(
        id="DBG002",
        name="Print Statement",
        category=CheckCategory.DEBUG,
        severity=CheckSeverity.WARN,
        pattern=r"^\s*print\s*\(",
        description="Print statement found",
        suggestion="Replace with proper logging",
        file_patterns=["*.py"],
    ),
    "DBG003": CheckDefinition(
        id="DBG003",
        name="Debugger Statement",
        category=CheckCategory.DEBUG,
        severity=CheckSeverity.BLOCK,
        pattern=r"\bdebugger\b|import\s+pdb|pdb\.set_trace\(\)",
        description="Debugger statement found",
        suggestion="Remove debugger statements before committing",
        file_patterns=["*.py", "*.js", "*.ts"],
    ),
    "DBG004": CheckDefinition(
        id="DBG004",
        name="TODO/FIXME Comment",
        category=CheckCategory.DEBUG,
        severity=CheckSeverity.INFO,
        pattern=r"(?i)#\s*(TODO|FIXME|XXX|HACK|BUG):",
        description="TODO/FIXME comment found",
        suggestion="Consider addressing before committing",
        file_patterns=["*.py", "*.js", "*.ts", "*.vue"],
    ),
    # Quality Checks
    "QUA001": CheckDefinition(
        id="QUA001",
        name="Empty Except Block",
        category=CheckCategory.QUALITY,
        severity=CheckSeverity.WARN,
        pattern=r"except\s*(?:\w+\s*)?:\s*(?:pass|\.\.\.)\s*$",
        description="Empty exception handler found",
        suggestion="Add proper error handling or logging",
        file_patterns=["*.py"],
    ),
    "QUA002": CheckDefinition(
        id="QUA002",
        name="Magic Number",
        category=CheckCategory.QUALITY,
        severity=CheckSeverity.INFO,
        pattern=r"(?<![a-zA-Z_])\b(?:(?!0|1|2|10|100|1000)\d{2,})\b(?!\s*[=:])",
        description="Magic number detected",
        suggestion="Extract to named constant",
        file_patterns=["*.py", "*.js", "*.ts"],
    ),
    "QUA003": CheckDefinition(
        id="QUA003",
        name="Long Line",
        category=CheckCategory.QUALITY,
        severity=CheckSeverity.INFO,
        pattern=r"^.{121,}$",
        description="Line exceeds 120 characters",
        suggestion="Break line for readability",
        file_patterns=["*.py"],
    ),
    # Style Checks
    "STY001": CheckDefinition(
        id="STY001",
        name="Trailing Whitespace",
        category=CheckCategory.STYLE,
        severity=CheckSeverity.INFO,
        pattern=r"[ \t]+$",
        description="Trailing whitespace detected",
        suggestion="Remove trailing whitespace",
        file_patterns=["*"],
    ),
    "STY002": CheckDefinition(
        id="STY002",
        name="Mixed Tabs and Spaces",
        category=CheckCategory.STYLE,
        severity=CheckSeverity.WARN,
        pattern=r"^(\t+ +| +\t+)",
        description="Mixed tabs and spaces in indentation",
        suggestion="Use consistent indentation",
        file_patterns=["*.py", "*.js", "*.ts"],
    ),
    # Documentation Checks
    "DOC001": CheckDefinition(
        id="DOC001",
        name="Missing Docstring",
        category=CheckCategory.DOCS,
        severity=CheckSeverity.INFO,
        pattern=r"^\s*def\s+(?!_)[a-zA-Z_]\w*\s*\([^)]*\)\s*:\s*$",
        description="Public function missing docstring",
        suggestion="Add docstring describing function purpose",
        file_patterns=["*.py"],
    ),
}

# In-memory storage for configuration
_hook_config = HookConfig()
_check_history: list[CommitCheckResult] = []

# Thread locks for safe access
_history_lock = threading.Lock()
_config_lock = threading.Lock()


# ============================================================================
# Helper Functions
# ============================================================================


def get_staged_files() -> list[str]:
    """Get list of staged files from git."""
    try:
        result = subprocess.run(  # nosec B607
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return [f for f in result.stdout.strip().split("\n") if f]
        return []
    except Exception as e:
        logger.warning("Failed to get staged files: %s", e)
        return []


def get_file_content(filepath: str) -> Optional[str]:
    """Get content of a file."""
    try:
        # Try to get staged content first
        result = subprocess.run(  # nosec B607
            ["git", "show", f":{filepath}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout
        # Fall back to file system
        path = Path(filepath)
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None
    except Exception as e:
        logger.warning("Failed to read file %s: %s", filepath, e)
        return None


def matches_file_pattern(filepath: str, patterns: list[str]) -> bool:
    """Check if filepath matches any of the patterns."""
    from fnmatch import fnmatch

    filename = Path(filepath).name
    for pattern in patterns:
        if pattern == "*" or fnmatch(filename, pattern) or fnmatch(filepath, pattern):
            return True
    return False


def run_check(check: CheckDefinition, filepath: str, content: str) -> list[CheckResult]:
    """Run a single check against file content."""
    results = []

    if not matches_file_pattern(filepath, check.file_patterns):
        return results

    try:
        pattern = re.compile(check.pattern, re.MULTILINE)
        lines = content.split("\n")

        for i, line in enumerate(lines, 1):
            matches = pattern.finditer(line)
            for _ in matches:  # Issue #382: match object unused
                # Get snippet context
                start = max(0, i - 2)
                end = min(len(lines), i + 1)
                snippet_lines = lines[start:end]
                snippet = "\n".join(
                    f"{start + j + 1}: {l}" for j, l in enumerate(snippet_lines)
                )

                results.append(
                    CheckResult(
                        check_id=check.id,
                        name=check.name,
                        category=check.category,
                        severity=check.severity,
                        passed=False,
                        message=check.description,
                        file=filepath,
                        line=i,
                        snippet=snippet,
                        suggestion=check.suggestion,
                    )
                )
    except re.error as e:
        logger.warning("Invalid regex in check %s: %s", check.id, e)

    return results


def _filter_enabled_checks(fast_mode: bool) -> dict:
    """
    Filter checks based on configuration and fast mode.

    Issue #620: Extracted from check_staged_files to reduce function length.

    Args:
        fast_mode: Whether to skip expensive checks

    Returns:
        Dictionary of enabled check IDs to PreCommitCheck objects
    """
    enabled_checks = {
        k: v
        for k, v in BUILTIN_CHECKS.items()
        if v.enabled and k not in _hook_config.disabled_checks
    }

    # If specific checks enabled, filter to those
    if _hook_config.enabled_checks:
        enabled_checks = {
            k: v for k, v in enabled_checks.items() if k in _hook_config.enabled_checks
        }

    # Skip expensive checks in fast mode (Issue #380: use module-level constant)
    if fast_mode:
        enabled_checks = {
            k: v for k, v in enabled_checks.items() if k not in _EXPENSIVE_CHECKS
        }

    return enabled_checks


def _calculate_check_statistics(
    results: list,
    enabled_checks: dict,
    staged_files: list,
    start_time,
) -> dict:
    """
    Calculate statistics from check results.

    Issue #620: Extracted from check_staged_files to reduce function length.

    Args:
        results: List of CheckResult objects
        enabled_checks: Dictionary of enabled checks
        staged_files: List of staged file paths
        start_time: When check started

    Returns:
        Dictionary with duration_ms, blocked, warnings, failed counts
    """
    duration_ms = (datetime.now() - start_time).total_seconds() * 1000
    blocked = any(r.severity == CheckSeverity.BLOCK and not r.passed for r in results)
    warnings = sum(
        1 for r in results if r.severity == CheckSeverity.WARN and not r.passed
    )
    failed = sum(1 for r in results if not r.passed)

    return {
        "duration_ms": round(duration_ms, 2),
        "blocked": blocked,
        "warnings": warnings,
        "failed": failed,
        "total_checks": len(enabled_checks) * len(staged_files),
        "passed_checks": len(enabled_checks) * len(staged_files) - failed,
    }


# ============================================================================
# API Endpoints
# ============================================================================


@router.get("/check")
async def check_staged_files(
    admin_check: bool = Depends(check_admin_permission),
    fast_mode: bool = Query(True, description="Skip expensive checks"),
) -> CommitCheckResult:
    """
    Check all staged files against pre-commit rules.

    Runs pattern checks on files staged for commit.
    Returns results with pass/fail status and detailed findings.

    Issue #744: Requires admin authentication.
    Issue #620: Refactored to use helper functions.
    """
    start_time = datetime.now()

    # Get staged files
    staged_files = get_staged_files()
    if not staged_files:
        staged_files = ["src/example.py", "src/config.js"]  # Demo mode

    # Filter enabled checks (Issue #620)
    enabled_checks = _filter_enabled_checks(fast_mode)

    # Run checks on all files
    results: list[CheckResult] = []
    for filepath in staged_files:
        content = get_file_content(filepath) or get_demo_content(filepath)
        for check in enabled_checks.values():
            results.extend(run_check(check, filepath, content))

    # Calculate statistics (Issue #620)
    stats = _calculate_check_statistics(results, enabled_checks, staged_files, start_time)

    result = CommitCheckResult(
        passed=not stats["blocked"],
        total_checks=stats["total_checks"],
        passed_checks=stats["passed_checks"],
        failed_checks=stats["failed"],
        warnings=stats["warnings"],
        blocked=stats["blocked"],
        duration_ms=stats["duration_ms"],
        results=results,
        files_checked=staged_files,
        timestamp=datetime.now().isoformat(),
    )

    # Store in history (thread-safe)
    with _history_lock:
        _check_history.insert(0, result)
        if len(_check_history) > 100:
            _check_history.pop()

    return result


@router.post("/check-content")
async def check_content(
    content: str,
    admin_check: bool = Depends(check_admin_permission),
    filepath: str = Query("untitled.py", description="Filename for pattern matching"),
) -> list[CheckResult]:
    """
    Check arbitrary content against pre-commit rules.

    Useful for checking content before staging.

    Issue #744: Requires admin authentication.
    """
    results: list[CheckResult] = []

    for check in BUILTIN_CHECKS.values():
        if check.enabled:
            check_results = run_check(check, filepath, content)
            results.extend(check_results)

    return results


@router.get("/checks")
async def list_checks(
    admin_check: bool = Depends(check_admin_permission),
) -> list[CheckDefinition]:
    """
    List all available pre-commit checks.

    Issue #744: Requires admin authentication.
    """
    return list(BUILTIN_CHECKS.values())


@router.get("/checks/{check_id}")
async def get_check(
    check_id: str,
    admin_check: bool = Depends(check_admin_permission),
) -> CheckDefinition:
    """
    Get details for a specific check.

    Issue #744: Requires admin authentication.
    """
    if check_id not in BUILTIN_CHECKS:
        raise HTTPException(status_code=404, detail=f"Check {check_id} not found")
    return BUILTIN_CHECKS[check_id]


@router.post("/checks/{check_id}/toggle")
async def toggle_check(
    check_id: str,
    enabled: bool,
    admin_check: bool = Depends(check_admin_permission),
) -> dict:
    """
    Enable or disable a specific check.

    Issue #744: Requires admin authentication.
    """
    if check_id not in BUILTIN_CHECKS:
        raise HTTPException(status_code=404, detail=f"Check {check_id} not found")

    BUILTIN_CHECKS[check_id].enabled = enabled

    return {
        "check_id": check_id,
        "enabled": enabled,
        "message": f"Check {check_id} {'enabled' if enabled else 'disabled'}",
    }


@router.get("/config")
async def get_config(
    admin_check: bool = Depends(check_admin_permission),
) -> HookConfig:
    """
    Get current hook configuration.

    Issue #744: Requires admin authentication.
    """
    with _config_lock:
        return _hook_config


@router.post("/config")
async def update_config(
    config: HookConfig,
    admin_check: bool = Depends(check_admin_permission),
) -> dict:
    """
    Update hook configuration.

    Issue #744: Requires admin authentication.
    """
    global _hook_config
    with _config_lock:
        _hook_config = config

    return {"message": "Configuration updated", "config": config}


@router.get("/status")
async def get_status(
    admin_check: bool = Depends(check_admin_permission),
) -> HookStatus:
    """
    Get status of installed pre-commit hooks.

    Issue #744: Requires admin authentication.
    """
    hook_path = Path(".git/hooks/pre-commit")
    # Issue #358 - avoid blocking
    installed = await asyncio.to_thread(hook_path.exists)

    version = None
    if installed:
        try:
            # Issue #358 - avoid blocking
            content = await asyncio.to_thread(hook_path.read_text)
            if "AutoBot" in content:
                version = "1.0.0"
        except Exception as e:
            logger.debug("Hook file unreadable: %s", e)

    last_run = None
    with _history_lock:
        if _check_history:
            last_run = _check_history[0].timestamp

    return HookStatus(
        installed=installed,
        path=str(hook_path) if installed else None,
        version=version,
        last_run=last_run,
        config=_hook_config,
    )


@router.post("/install")
async def install_hooks(
    admin_check: bool = Depends(check_admin_permission),
) -> dict:
    """
    Install pre-commit hooks.

    Issue #744: Requires admin authentication.
    """
    hook_path = Path(".git/hooks/pre-commit")

    # Check if .git exists
    # Issue #358 - avoid blocking
    if not await asyncio.to_thread(Path(".git").exists):
        raise HTTPException(status_code=400, detail="Not a git repository")

    # Create hooks directory if needed
    # Issue #358 - avoid blocking
    await asyncio.to_thread(hook_path.parent.mkdir, parents=True, exist_ok=True)

    # Create pre-commit hook script with dynamic port from NetworkConstants
    backend_port = NetworkConstants.BACKEND_PORT
    hook_content = f"""#!/bin/bash
# AutoBot Pre-commit Hook v1.0.0
# Copyright (c) 2025 mrveiss

# Colors
RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[0;33m'
NC='\\033[0m'

# Check for bypass keyword in commit message
if git log -1 --format=%B 2>/dev/null | grep -q "\\[skip-hooks\\]"; then
    echo -e "${{YELLOW}}Pre-commit hooks bypassed${{NC}}"
    exit 0
fi

# Run AutoBot pre-commit check
echo "Running AutoBot pre-commit checks..."

# Try API first
RESULT=$(curl -s -X GET "http://localhost:{backend_port}/api/precommit/check?fast_mode=true" 2>/dev/null)

if [ $? -eq 0 ] && [ -n "$RESULT" ]; then
    PASSED=$(echo "$RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('passed', True))" 2>/dev/null)
    BLOCKED=$(echo "$RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('blocked', False))" 2>/dev/null)
    FAILED=$(echo "$RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('failed_checks', 0))" 2>/dev/null)
    DURATION=$(echo "$RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('duration_ms', 0))" 2>/dev/null)

    if [ "$BLOCKED" = "True" ]; then
        echo -e "${{RED}}Pre-commit checks failed!${{NC}}"
        echo -e "Found ${{FAILED}} issues (${{DURATION}}ms)"
        echo ""
        echo "View details: curl http://localhost:{backend_port}/api/precommit/check"
        echo "Bypass with: git commit --message '[skip-hooks] your message'"
        exit 1
    elif [ "$FAILED" != "0" ]; then
        echo -e "${{YELLOW}}Pre-commit warnings: ${{FAILED}} issues found${{NC}}"
        echo -e "Completed in ${{DURATION}}ms"
    else
        echo -e "${{GREEN}}All pre-commit checks passed${{NC}} (${{DURATION}}ms)"
    fi
else
    echo -e "${{YELLOW}}AutoBot API not available - skipping checks${{NC}}"
fi

exit 0
"""

    try:
        # Issue #358 - avoid blocking
        await asyncio.to_thread(hook_path.write_text, hook_content)
        await asyncio.to_thread(hook_path.chmod, 0o755)

        return {
            "success": True,
            "message": "Pre-commit hooks installed successfully",
            "path": str(hook_path),
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to install hooks: {str(e)}"
        )


@router.post("/uninstall")
async def uninstall_hooks(
    admin_check: bool = Depends(check_admin_permission),
) -> dict:
    """
    Uninstall pre-commit hooks.

    Issue #744: Requires admin authentication.
    """
    hook_path = Path(".git/hooks/pre-commit")

    # Issue #358 - avoid blocking
    if not await asyncio.to_thread(hook_path.exists):
        return {"success": True, "message": "No hooks to uninstall"}

    try:
        # Check if it's our hook
        # Issue #358 - avoid blocking
        content = await asyncio.to_thread(hook_path.read_text)
        if "AutoBot" not in content:
            raise HTTPException(
                status_code=400,
                detail="Pre-commit hook is not from AutoBot - will not remove",
            )

        # Issue #358 - avoid blocking
        await asyncio.to_thread(hook_path.unlink)
        return {"success": True, "message": "Pre-commit hooks uninstalled"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to uninstall hooks: {str(e)}"
        )


@router.get("/history")
async def get_history(
    admin_check: bool = Depends(check_admin_permission),
    limit: int = Query(20, ge=1, le=100, description="Number of results"),
) -> list[CommitCheckResult]:
    """
    Get recent pre-commit check history.

    Issue #744: Requires admin authentication.
    """
    with _history_lock:
        return _check_history[:limit]


@router.get("/summary")
async def get_summary(
    admin_check: bool = Depends(check_admin_permission),
) -> dict:
    """
    Get summary of pre-commit checks.

    Issue #744: Requires admin authentication.
    """
    # Thread-safe copy for processing
    with _history_lock:
        history_copy = list(_check_history)

    total_checks = len(history_copy)
    if total_checks == 0:
        return {
            "total_runs": 0,
            "pass_rate": 0,
            "average_duration_ms": 0,
            "common_issues": [],
        }

    passed = sum(1 for r in history_copy if r.passed)
    avg_duration = sum(r.duration_ms for r in history_copy) / total_checks

    # Count issue frequency
    issue_counts: dict[str, int] = {}
    for run in history_copy:
        for result in run.results:
            if not result.passed:
                key = result.check_id
                issue_counts[key] = issue_counts.get(key, 0) + 1

    common_issues = [
        {
            "check_id": k,
            "count": v,
            "name": BUILTIN_CHECKS.get(
                k,
                CheckDefinition(
                    id=k,
                    name=k,
                    category=CheckCategory.QUALITY,
                    severity=CheckSeverity.INFO,
                    pattern="",
                    description="",
                    suggestion="",
                ),
            ).name,
        }
        for k, v in sorted(issue_counts.items(), key=lambda x: -x[1])[:10]
    ]

    return {
        "total_runs": total_checks,
        "pass_rate": round(passed / total_checks * 100, 1),
        "average_duration_ms": round(avg_duration, 2),
        "common_issues": common_issues,
        "checks_enabled": sum(1 for c in BUILTIN_CHECKS.values() if c.enabled),
        "total_checks": len(BUILTIN_CHECKS),
    }


@router.get("/categories")
async def get_categories(
    admin_check: bool = Depends(check_admin_permission),
) -> list[dict]:
    """
    Get check categories with counts.

    Issue #744: Requires admin authentication.
    """
    category_counts: dict[str, dict] = {}

    for check in BUILTIN_CHECKS.values():
        cat = check.category.value
        if cat not in category_counts:
            category_counts[cat] = {"enabled": 0, "disabled": 0}

        if check.enabled:
            category_counts[cat]["enabled"] += 1
        else:
            category_counts[cat]["disabled"] += 1

    return [
        {
            "category": cat,
            "enabled": counts["enabled"],
            "disabled": counts["disabled"],
            "total": counts["enabled"] + counts["disabled"],
        }
        for cat, counts in category_counts.items()
    ]


# ============================================================================
# Demo Content
# ============================================================================


def get_demo_content(filepath: str) -> str:
    """Get demo content for testing."""
    if filepath.endswith(".py"):
        return """
import os

# Configuration
password = "admin123"  # TODO: move to env
api_key = "sk-1234567890abcdef1234567890abcdef"

def process_data(items):
    for item in items:
        logger.info("Processing: {item}")  # Debug print
        try:
            result = transform(item)
        except:
            pass  # Empty except block

    return 42  # Magic number

def helper():
    pass
"""
    elif filepath.endswith(".js") or filepath.endswith(".ts"):
        return """
const API_KEY = "secret-api-key-12345678901234";

function processData(items) {
    console.log("Starting process");
    debugger;

    for (const item of items) {
        console.debug(item);
    }

    return items.length;
}
"""
    return ""
