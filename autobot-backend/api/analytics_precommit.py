# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Git Pre-commit Hook Analyzer API

Issue #223: Implements git hooks that check for patterns before allowing commits.
Features fast pattern checking, clear error messages, and bypass mechanism.
"""

import asyncio
import subprocess  # nosec B404
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from api.schemas_analytics import (
    CheckCategory,
    CheckDefinition,
    CheckResult,
    CheckSeverity,
    CheckToggleResponse,
    CommitCheckResult,
    HookConfig,
    HookConfigUpdateResponse,
    HookInstallResponse,
    HookStatus,
    PrecommitCategoryItem,
    PrecommitSummaryResponse,
)
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from code_intelligence.precommit_analyzer import BUILTIN_CHECKS as _ENGINE_BUILTIN_CHECKS
from code_intelligence.precommit_analyzer import CheckDefinition as _EngineCheckDefinition
from code_intelligence.precommit_analyzer import CheckResult as _EngineCheckResult
from code_intelligence.precommit_analyzer import PrecommitAnalyzer
from constants.network_constants import NetworkConstants

logger = get_logger(__name__)

router = APIRouter(tags=["precommit", "analytics"])  # Prefix set in router_registry


# ============================================================================
# Check Definitions
# ============================================================================

# ---------------------------------------------------------------------------
# Single source of truth (#9873): this module is a thin HTTP layer over the
# analyzer engine (code_intelligence.precommit_analyzer). Both the check
# *catalog* (BUILTIN_CHECKS) and check *execution* are delegated to the engine
# via PrecommitAnalyzer, so the API can never drift from what actually runs.
# Previously this module kept its own hand-copied catalog AND a duplicate
# regex runner, which had forked (stale catalog, conflicting QUA002/SEC004
# definitions, a fast-mode skip list that no longer matched, and a runner that
# could not execute the engine's multiline checks).
# ---------------------------------------------------------------------------


def _engine_check_to_schema(check: _EngineCheckDefinition) -> CheckDefinition:
    """Convert an engine ``CheckDefinition`` (dataclass) to the API schema model.

    Engine and API enums share identical values but are distinct classes, so
    they are mapped by ``.value``. The engine-only ``multiline`` flag has no API
    schema field (the engine owns execution, so the API never needs it).
    """
    return CheckDefinition(
        id=check.id,
        name=check.name,
        category=CheckCategory(check.category.value),
        severity=CheckSeverity(check.severity.value),
        pattern=check.pattern,
        description=check.description,
        suggestion=check.suggestion,
        file_patterns=list(check.file_patterns),
        enabled=check.enabled,
    )


BUILTIN_CHECKS: dict[str, CheckDefinition] = {
    check_id: _engine_check_to_schema(check) for check_id, check in _ENGINE_BUILTIN_CHECKS.items()
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
        result = subprocess.run(  # nosec B603 B607 - fixed argv, no user input
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


def get_file_content(filepath: str) -> str | None:
    """Get content of a file."""
    try:
        # Try to get staged content first
        result = subprocess.run(  # nosec B603 B607 - fixed argv, no user input
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


def _engine_result_to_schema(result: _EngineCheckResult) -> CheckResult:
    """Convert an engine ``CheckResult`` (dataclass) to the API schema model."""
    return CheckResult(
        check_id=result.check_id,
        name=result.name,
        category=CheckCategory(result.category.value),
        severity=CheckSeverity(result.severity.value),
        passed=result.passed,
        message=result.message,
        file=result.file_path or None,
        line=result.line,
        snippet=result.snippet or None,
        suggestion=result.suggestion or None,
    )


def _active_engine_checks(fast_mode: bool) -> dict[str, _EngineCheckDefinition]:
    """Engine check definitions the API should run for a request.

    Honors the API's enable/disable configuration (the per-check ``enabled``
    toggle plus the ``HookConfig`` allow/deny lists) and, in fast mode, the
    engine's own expensive-check set — so catalog, skip list and runner all
    stay sourced from the engine and can never disagree (#9873).
    """
    expensive = PrecommitAnalyzer().expensive_checks
    active: dict[str, _EngineCheckDefinition] = {}
    for check_id, engine_check in _ENGINE_BUILTIN_CHECKS.items():
        if not BUILTIN_CHECKS[check_id].enabled:
            continue
        if check_id in _hook_config.disabled_checks:
            continue
        if _hook_config.enabled_checks and check_id not in _hook_config.enabled_checks:
            continue
        if fast_mode and check_id in expensive:
            continue
        active[check_id] = engine_check
    return active


def _run_engine_checks(active_checks: dict, filepath: str, content: str) -> list[CheckResult]:
    """Execute the given engine checks against content via the engine analyzer.

    The duplicate API runner was removed (#9873): execution is delegated to
    PrecommitAnalyzer so multiline checks, patterns and severities always match
    what the engine actually enforces. ``active_checks`` is already filtered, so
    the analyzer runs with ``fast_mode=False`` to avoid double-filtering.
    """
    analyzer = PrecommitAnalyzer(checks=active_checks, fast_mode=False)
    return [_engine_result_to_schema(r) for r in analyzer.analyze_content(content, filepath)]


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
    duration_ms = (datetime.now(tz=timezone.utc) - start_time).total_seconds() * 1000
    blocked = any(r.severity == CheckSeverity.BLOCK and not r.passed for r in results)
    warnings = sum(1 for r in results if r.severity == CheckSeverity.WARN and not r.passed)
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


@router.get("/check", response_model=CommitCheckResult)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="check_staged_files",
    error_code_prefix="ANALYTICS_PRECOMMIT",
)
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
    start_time = datetime.now(tz=timezone.utc)

    # Get staged files
    staged_files = get_staged_files()
    if not staged_files:
        staged_files = ["src/example.py", "src/config.js"]  # Demo mode

    # Engine-delegated execution (#9873): the set of checks to run and the
    # runner both come from the analyzer engine.
    enabled_checks = _active_engine_checks(fast_mode)

    # Run checks on all files via the engine analyzer
    results: list[CheckResult] = []
    for filepath in staged_files:
        content = get_file_content(filepath) or get_demo_content(filepath)
        results.extend(_run_engine_checks(enabled_checks, filepath, content))

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
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
    )

    # Store in history (thread-safe)
    with _history_lock:
        _check_history.insert(0, result)
        if len(_check_history) > 100:
            _check_history.pop()

    return result


@router.post("/check-content", response_model=list[CheckResult])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="check_content",
    error_code_prefix="ANALYTICS_PRECOMMIT",
)
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
    # Engine-delegated execution (#9873). fast_mode is not applied here — this
    # endpoint has always run every enabled check against the supplied content.
    return _run_engine_checks(_active_engine_checks(fast_mode=False), filepath, content)


@router.get("/checks", response_model=list[CheckDefinition])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_checks",
    error_code_prefix="ANALYTICS_PRECOMMIT",
)
async def list_checks(
    admin_check: bool = Depends(check_admin_permission),
) -> list[CheckDefinition]:
    """
    List all available pre-commit checks.

    Issue #744: Requires admin authentication.
    """
    return list(BUILTIN_CHECKS.values())


@router.get("/checks/{check_id}", response_model=CheckDefinition)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_check",
    error_code_prefix="ANALYTICS_PRECOMMIT",
)
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


@router.post("/checks/{check_id}/toggle", response_model=CheckToggleResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="toggle_check",
    error_code_prefix="ANALYTICS_PRECOMMIT",
)
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


@router.get("/config", response_model=HookConfig)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_config",
    error_code_prefix="ANALYTICS_PRECOMMIT",
)
async def get_config(
    admin_check: bool = Depends(check_admin_permission),
) -> HookConfig:
    """
    Get current hook configuration.

    Issue #744: Requires admin authentication.
    """
    with _config_lock:
        return _hook_config


@router.post("/config", response_model=HookConfigUpdateResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_config",
    error_code_prefix="ANALYTICS_PRECOMMIT",
)
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


@router.get("/status", response_model=HookStatus)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_status",
    error_code_prefix="ANALYTICS_PRECOMMIT",
)
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


def _generate_precommit_hook_script(backend_port: int) -> str:
    """
    Generate the pre-commit hook bash script content.

    Issue #620: Extracted from install_hooks to reduce function length.

    Args:
        backend_port: Backend API port for curl requests

    Returns:
        Bash script content for pre-commit hook
    """
    return f"""#!/bin/bash  # noqa: E501
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
    PASSED=$(echo "$RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('passed', True))" 2>/dev/null)  # noqa: print
    BLOCKED=$(echo "$RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('blocked', False))" 2>/dev/null)  # noqa: print
    FAILED=$(echo "$RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('failed_checks', 0))" 2>/dev/null)  # noqa: print
    DURATION=$(echo "$RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('duration_ms', 0))" 2>/dev/null)  # noqa: print

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


async def _write_hook_file(hook_path: Path, content: str) -> dict:
    """
    Write hook file with proper permissions.

    Issue #620: Extracted from install_hooks to reduce function length.

    Args:
        hook_path: Path to hook file
        content: Hook script content

    Returns:
        Success response dict

    Raises:
        HTTPException: If writing fails
    """
    try:
        await asyncio.to_thread(hook_path.write_text, content)
        await asyncio.to_thread(hook_path.chmod, 0o755)

        return {
            "success": True,
            "message": "Pre-commit hooks installed successfully",
            "path": str(hook_path),
        }
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to install hooks")


@router.post("/install", response_model=HookInstallResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="install_hooks",
    error_code_prefix="ANALYTICS_PRECOMMIT",
)
async def install_hooks(
    admin_check: bool = Depends(check_admin_permission),
) -> dict:
    """
    Install pre-commit hooks.

    Issue #744: Requires admin authentication.
    Issue #620: Refactored to use helper functions.
    """
    hook_path = Path(".git/hooks/pre-commit")

    # Check if .git exists - Issue #358: avoid blocking
    if not await asyncio.to_thread(Path(".git").exists):
        raise HTTPException(status_code=400, detail="Not a git repository")

    # Create hooks directory if needed - Issue #358: avoid blocking
    await asyncio.to_thread(hook_path.parent.mkdir, parents=True, exist_ok=True)

    # Generate and write hook script - Issue #620: Use helpers
    hook_content = _generate_precommit_hook_script(NetworkConstants.BACKEND_PORT)
    return await _write_hook_file(hook_path, hook_content)


@router.post("/uninstall", response_model=HookInstallResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="uninstall_hooks",
    error_code_prefix="ANALYTICS_PRECOMMIT",
)
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
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to uninstall hooks")


@router.get("/history", response_model=list[CommitCheckResult])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_history",
    error_code_prefix="ANALYTICS_PRECOMMIT",
)
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


@router.get("/summary", response_model=PrecommitSummaryResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_summary",
    error_code_prefix="ANALYTICS_PRECOMMIT",
)
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
            "pass_rate": 0,  # nosec B105 - dict key 'pass_rate' with numeric value, not a password
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


@router.get("/categories", response_model=list[PrecommitCategoryItem])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_categories",
    error_code_prefix="ANALYTICS_PRECOMMIT",
)
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
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

# Configuration
password = "admin123"  # noqa: S105 — intentional demo credential for analyzer testing
api_key = "sk-1234567890abcdef1234567890abcdef"  # noqa: S105 — intentional demo credential

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
