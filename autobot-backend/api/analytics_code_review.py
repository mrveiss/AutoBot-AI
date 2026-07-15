# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
AI-Powered Code Review Automation API (Issue #225)

Provides automated code review with pattern checking, security analysis,
and AI-generated review comments. Learns from past reviews.
"""

import asyncio
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Query

from api.analytics_shared import (  # noqa: F401 – used by history/metrics/summary
    resolve_source_or_404 as _resolve_source_or_404,
)
from api.analytics_shared import resolve_source_root_or_404 as _resolve_source_root_or_404
from api.schemas_analytics import (
    CodeReviewCategoryItem,
    CodeReviewPatternItem,
    PatternToggleRequest,
    ReviewCategory,
    ReviewComment,
    ReviewSeverity,
)
from api.schemas_code import (
    CodeReviewAnalyzeResponse,
    CodeReviewFeedbackResponse,
    CodeReviewFileResponse,
    CodeReviewHistoryResponse,
    CodeReviewMetricsResponse,
    CodeReviewPatternPreferencesResponse,
    CodeReviewPatternToggleResponse,
    CodeReviewReviewByIdResponse,
    CodeReviewSummaryResponse,
)
from auth_middleware import check_admin_permission, get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import parse_utc_iso
from constants.threshold_constants import TimingConstants
from constants.ttl_constants import TTL_7_DAYS

logger = get_logger(__name__)

# Allowlist pattern for git commit range arguments (Issue #1733).
# Allows: HEAD, HEAD~N, commit hashes, branch names, .. and ... range operators.
_VALID_GIT_REF_RE = re.compile(r"^[a-zA-Z0-9_./@{}^~-]+(?:\.{2,3}[a-zA-Z0-9_./@{}^~-]+)?$")

router = APIRouter(tags=["code-review", "analytics"])  # Prefix set in router_registry

# Performance optimization: O(1) lookup for reviewable file extensions (Issue #326)
REVIEWABLE_EXTENSIONS = {".py", ".vue", ".ts", ".js"}

# Issue #380: Pre-compiled regex patterns for code review
_HUNK_HEADER_RE = re.compile(r"@@ -(\d+),?\d* \+(\d+),?\d* @@")
_FUNC_DEFINITION_RE = re.compile(r"^(async\s+)?def\s+(\w+)\s*\(", re.MULTILINE)
_NEXT_TOPLEVEL_RE = re.compile(r"\n(?=\S)")


# ============================================================================
# Models
# ============================================================================


# ============================================================================
# Pattern Definitions
# ============================================================================


REVIEW_PATTERNS = {
    # Security patterns
    "SEC001": {
        "name": "Hardcoded Secret",
        "pattern": r'(password|secret|api_key|token)\s*=\s*["\'][^"\']+["\']',
        "category": ReviewCategory.SECURITY,
        "severity": ReviewSeverity.CRITICAL,
        "message": "Potential hardcoded secret detected. Use environment variables.",
        "suggestion": "Move this value to an environment variable or secrets manager.",
    },
    "SEC002": {
        "name": "SQL Injection Risk",
        "pattern": r'execute\s*\(\s*[f"\'].*\{.*\}.*["\']',
        "category": ReviewCategory.SECURITY,
        "severity": ReviewSeverity.CRITICAL,
        "message": "Potential SQL injection vulnerability. Use parameterized queries.",
        "suggestion": "Use query parameters instead of string formatting.",
    },
    "SEC003": {
        "name": "Unsafe eval",
        "pattern": r"\beval\s*\(",
        "category": ReviewCategory.SECURITY,
        "severity": ReviewSeverity.CRITICAL,
        "message": "Use of eval() is a security risk. Avoid if possible.",
        "suggestion": "Use ast.literal_eval() for safe evaluation or refactor to avoid eval.",
    },
    # Performance patterns
    "PERF001": {
        "name": "N+1 Query Pattern",
        "pattern": r"for\s+\w+\s+in\s+\w+:.*\n.*\.(get|filter|select)",
        "category": ReviewCategory.PERFORMANCE,
        "severity": ReviewSeverity.WARNING,
        "message": "Potential N+1 query pattern. Consider using bulk operations.",
        "suggestion": "Use prefetch_related or select_related to optimize queries.",
    },
    "PERF002": {
        "name": "Large list in memory",
        "pattern": r"list\(\w+\.objects\.all\(\)\)",
        "category": ReviewCategory.PERFORMANCE,
        "severity": ReviewSeverity.WARNING,
        "message": "Loading entire queryset into memory. Consider pagination.",
        "suggestion": "Use iterator() or pagination for large datasets.",
    },
    # Style patterns
    "STYLE001": {
        "name": "Magic Number",
        "pattern": r"(?<![\w])(?:if|elif|while|for|return)\s+.*[^0-9]\d{2,}[^0-9]",
        "category": ReviewCategory.STYLE,
        "severity": ReviewSeverity.SUGGESTION,
        "message": "Magic number detected. Consider using a named constant.",
        "suggestion": "Extract this value to a named constant for better readability.",
    },
    "STYLE002": {
        "name": "Long Function",
        "pattern": None,  # Checked programmatically
        "category": ReviewCategory.MAINTAINABILITY,
        "severity": ReviewSeverity.WARNING,
        "message": "Function exceeds 50 lines. Consider breaking it down.",
        "suggestion": "Extract logical sections into smaller helper functions.",
    },
    # Bug risk patterns
    "BUG001": {
        "name": "Empty except block",
        "pattern": r"except\s*:\s*\n\s*(pass|\.\.\.)",
        "category": ReviewCategory.BUG_RISK,
        "severity": ReviewSeverity.WARNING,
        "message": "Empty except block silently swallows all exceptions.",
        "suggestion": "Log the exception or handle it explicitly.",
    },
    "BUG002": {
        "name": "Mutable default argument",
        "pattern": r"def\s+\w+\s*\([^)]*=\s*(\[\]|\{\}|set\(\))",
        "category": ReviewCategory.BUG_RISK,
        "severity": ReviewSeverity.WARNING,
        "message": "Mutable default argument can cause unexpected behavior.",
        "suggestion": "Use None as default and initialize inside the function.",
    },
    # Documentation patterns
    "DOC001": {
        "name": "Missing docstring",
        "pattern": r'def\s+[a-z_]\w*\s*\([^)]*\):\s*\n\s+(?!""")',
        "category": ReviewCategory.DOCUMENTATION,
        "severity": ReviewSeverity.INFO,
        "message": "Public function missing docstring.",
        "suggestion": "Add a docstring describing the function's purpose and parameters.",
    },
    # Testing patterns
    "TEST001": {
        "name": "No assertions",
        "pattern": r"def\s+test_\w+\([^)]*\):[^}]+(?<!assert)",
        "category": ReviewCategory.TESTING,
        "severity": ReviewSeverity.WARNING,
        "message": "Test function appears to have no assertions.",
        "suggestion": "Add assert statements to verify expected behavior.",
    },
    # Best practice patterns
    "BP001": {
        "name": "Print statement",
        "pattern": r"(?<!#.*)\bprint\s*\(",
        "category": ReviewCategory.BEST_PRACTICE,
        "severity": ReviewSeverity.SUGGESTION,
        "message": "Print statement found. Use logging for production code.",
        "suggestion": "Replace with logger.info() or logger.debug().",
    },
    "BP002": {
        "name": "TODO comment",
        "pattern": r"#\s*TODO",
        "category": ReviewCategory.BEST_PRACTICE,
        "severity": ReviewSeverity.INFO,
        "message": "TODO comment found. Consider creating an issue.",
        "suggestion": "Create a GitHub issue to track this work.",
    },
}


# ============================================================================
# Utility Functions
# ============================================================================


def _no_data_response(
    message: str = "No code review data. Run a code review first.",
) -> dict:
    """Standardized no-data response (Issue #543)."""
    return {
        "status": "no_data",
        "message": message,
        "review": None,
        "comments": [],
        "summary": {},
    }


def _parse_hunk_header(line: str) -> dict[str, Any] | None:
    """Parse a diff hunk header line (Issue #315)."""
    match = _HUNK_HEADER_RE.match(line)
    if match:
        return {
            "old_start": int(match.group(1)),
            "new_start": int(match.group(2)),
            "lines": [],
        }
    return None


def _classify_diff_line(line: str) -> tuple[str, str]:
    """Classify a diff line and extract content (Issue #315)."""
    if line.startswith("+") and not line.startswith("+++"):
        return "add", line[1:]
    elif line.startswith("-") and not line.startswith("---"):
        return "delete", line[1:]
    return "context", line[1:] if line else ""


def parse_diff(diff_content: str) -> list[dict[str, Any]]:
    """Parse unified diff format into structured data (Issue #315: depth 7→3)."""
    files = []
    current_file = None
    current_hunks = []
    current_hunk = None

    for line in diff_content.split("\n"):
        # Handle new file marker
        if line.startswith("diff --git"):
            if current_file:
                current_file["hunks"] = current_hunks
                files.append(current_file)
            parts = line.split(" b/")
            file_path = parts[-1] if len(parts) > 1 else "unknown"
            current_file = {
                "path": file_path,
                "hunks": [],
                "additions": 0,
                "deletions": 0,
            }
            current_hunks = []
            current_hunk = None
            continue

        # Handle hunk header
        if line.startswith("@@"):
            if current_hunk:
                current_hunks.append(current_hunk)
            current_hunk = _parse_hunk_header(line)
            continue

        # Handle content lines within a hunk
        if current_hunk is None:
            continue

        line_type, content = _classify_diff_line(line)
        current_hunk["lines"].append({"type": line_type, "content": content})
        if current_file and line_type == "add":
            current_file["additions"] += 1
        elif current_file and line_type == "delete":
            current_file["deletions"] += 1

    # Add last file and hunk
    if current_hunk:
        current_hunks.append(current_hunk)
    if current_file:
        current_file["hunks"] = current_hunks
        files.append(current_file)

    return files


def analyze_code(content: str, file_path: str) -> list[ReviewComment]:
    """Analyze code content for pattern violations."""
    comments = []
    lines = content.split("\n")

    for pattern_id, pattern_def in REVIEW_PATTERNS.items():
        if pattern_def.get("pattern"):
            try:
                for match in re.finditer(pattern_def["pattern"], content, re.IGNORECASE | re.MULTILINE):
                    # Calculate line number
                    line_num = content[: match.start()].count("\n") + 1
                    code_snippet = lines[line_num - 1] if line_num <= len(lines) else ""

                    comments.append(
                        ReviewComment(
                            id=f"{pattern_id}-{line_num}",
                            file_path=file_path,
                            line_number=line_num,
                            severity=pattern_def["severity"],
                            category=pattern_def["category"],
                            message=pattern_def["message"],
                            suggestion=pattern_def.get("suggestion"),
                            code_snippet=code_snippet.strip(),
                            pattern_id=pattern_id,
                        )
                    )
            except re.error:
                logger.warning("Invalid regex pattern: %s", pattern_id)

    # Check for long functions
    for match in _FUNC_DEFINITION_RE.finditer(content):
        func_start = content[: match.start()].count("\n") + 1
        # Find function end (simple heuristic)
        remaining = content[match.end() :]
        indent_match = _NEXT_TOPLEVEL_RE.search(remaining)
        if indent_match:
            func_end = func_start + remaining[: indent_match.start()].count("\n")
            if func_end - func_start > 50:
                func_length = func_end - func_start
                func_name = match.group(2)
                message = f"Function '{func_name}' is {func_length} lines long. Consider refactoring."
                comments.append(
                    ReviewComment(
                        id=f"STYLE002-{func_start}",
                        file_path=file_path,
                        line_number=func_start,
                        severity=ReviewSeverity.WARNING,
                        category=ReviewCategory.MAINTAINABILITY,
                        message=message,
                        suggestion="Break this function into smaller, focused functions.",
                        pattern_id="STYLE002",
                    )
                )

    return comments


def calculate_review_score(comments: list[ReviewComment]) -> float:
    """Calculate overall code quality score based on findings."""
    if not comments:
        return 100.0

    # Severity weights
    weights = {
        ReviewSeverity.CRITICAL: 15,
        ReviewSeverity.WARNING: 5,
        ReviewSeverity.INFO: 1,
        ReviewSeverity.SUGGESTION: 0.5,
    }

    total_deduction = sum(weights.get(c.severity, 1) for c in comments)
    score = max(0, 100 - total_deduction)
    return round(score, 1)


def generate_summary(comments: list[ReviewComment]) -> dict[str, Any]:
    """Generate review summary statistics."""
    by_severity = {}
    by_category = {}

    for comment in comments:
        # Count by severity
        sev = comment.severity.value
        by_severity[sev] = by_severity.get(sev, 0) + 1

        # Count by category
        cat = comment.category.value
        by_category[cat] = by_category.get(cat, 0) + 1

    return {
        "by_severity": by_severity,
        "by_category": by_category,
        "critical_count": by_severity.get("critical", 0),
        "warning_count": by_severity.get("warning", 0),
        "info_count": by_severity.get("info", 0) + by_severity.get("suggestion", 0),
        "top_issues": [
            {"category": cat, "count": count}
            for cat, count in sorted(by_category.items(), key=lambda x: x[1], reverse=True)[:5]
        ],
    }


async def get_git_diff(commit_range: str | None = None) -> str:
    """Get git diff for review."""
    try:
        cmd = ["git", "diff"]
        if commit_range:
            if not _VALID_GIT_REF_RE.match(commit_range):
                logger.warning("Rejected invalid git commit range: %s", commit_range)
                return ""
            cmd.append(commit_range)
        else:
            cmd.append("HEAD~1..HEAD")

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=TimingConstants.SHORT_TIMEOUT)
            return stdout.decode("utf-8") if process.returncode == 0 else ""
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            logger.warning("Git diff timed out after %s seconds", TimingConstants.SHORT_TIMEOUT)
            return ""
    except Exception as e:
        logger.warning("Failed to get git diff: %s", e)
        return ""


# ============================================================================
# REST Endpoints
# ============================================================================


@router.get("/analyze", response_model=CodeReviewAnalyzeResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_diff",
    error_code_prefix="ANALYTICS_CODE_REVIEW",
)
async def analyze_diff(
    admin_check: bool = Depends(check_admin_permission),
    commit_range: str | None = Query(None, description="Git commit range (e.g., HEAD~1..HEAD)"),
    source_id: str | None = Query(None, description="Project source ID to scope analysis"),
) -> dict[str, Any]:
    """
    Analyze git diff and generate review comments.

    Issue #744: Requires admin authentication.
    Issue #3441: When source_id is supplied, only files under that project's
    clone directory (source_root) are analysed.  Files outside source_root
    are skipped so results are scoped to the selected project.

    Returns review findings with severity and suggestions.
    """
    # source_root and diff_content have no data dependency — parallelize the I/O.
    source_root, diff_content = await asyncio.gather(
        _resolve_source_root_or_404(source_id),
        get_git_diff(commit_range),
    )

    if not diff_content:
        # Issue #543: Return no-data response instead of demo data
        return _no_data_response("No git diff available. Make changes or specify a commit range.")

    # Parse diff
    files = parse_diff(diff_content)

    # Analyze each file
    all_comments = []
    for file_info in files:
        # Get full file content for analysis
        try:
            file_path = Path(file_info["path"])
            # Issue #3441: restrict to source_root when provided
            if source_root is not None:
                resolved = file_path.resolve()
                try:
                    resolved.relative_to(source_root.resolve())
                except ValueError:
                    logger.debug("Skipping file outside source_root: %s", file_info["path"])
                    continue
            # Issue #358 - avoid blocking
            if await asyncio.to_thread(file_path.exists) and file_path.suffix in REVIEWABLE_EXTENSIONS:
                content = await asyncio.to_thread(file_path.read_text, encoding="utf-8", errors="ignore")
                comments = analyze_code(content, str(file_path))
                all_comments.extend(comments)
        except Exception as e:
            logger.warning("Failed to analyze %s: %s", file_info["path"], e)

    score = calculate_review_score(all_comments)
    summary = generate_summary(all_comments)

    review_id = str(uuid.uuid4())
    analyzed_at = datetime.now(tz=timezone.utc).isoformat()
    result_payload = {
        "id": review_id,
        "path": commit_range or "HEAD~1..HEAD",
        "issues": [c.model_dump() for c in all_comments],
        "analyzed_at": analyzed_at,
        "files_reviewed": len(files),
        "score": score,
        "summary": summary,
    }

    try:
        from autobot_shared.redis_client import get_redis_client

        redis = get_redis_client(async_client=False, database="analytics")
        if redis:
            effective_source = source_id or "default"
            redis_key = f"code_review:result:{effective_source}:{review_id}"
            history_entry = {
                "id": review_id,
                "path": result_payload["path"],
                "analyzed_at": analyzed_at,
                "total_comments": len(all_comments),
                "score": score,
                "source_id": effective_source,
            }
            # redis.set writes to a different key than history ops — parallelize round-trips.
            await asyncio.gather(
                asyncio.to_thread(redis.set, redis_key, json.dumps(result_payload), "ex", TTL_7_DAYS),
                asyncio.to_thread(redis.lpush, f"code_review:history:{effective_source}", json.dumps(history_entry)),
            )
            # ltrim and expire both require lpush to have created the key first;
            # they are independent of each other so run them concurrently.
            await asyncio.gather(
                asyncio.to_thread(redis.ltrim, f"code_review:history:{effective_source}", 0, 99),
                asyncio.to_thread(redis.expire, f"code_review:history:{effective_source}", TTL_7_DAYS),
            )
            logger.info("Stored code review result %s for source %s", review_id, effective_source)
    except Exception as exc:
        logger.warning("Failed to persist code review result: %s", exc)

    return {
        "status": "success",
        "id": review_id,
        "timestamp": analyzed_at,
        "files_reviewed": len(files),
        "total_comments": len(all_comments),
        "score": score,
        "comments": [c.model_dump() for c in all_comments],
        "summary": summary,
    }


@router.get("/review/{review_id}", response_model=CodeReviewReviewByIdResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_review_by_id",
    error_code_prefix="ANALYTICS_CODE_REVIEW",
)
async def get_review_by_id(
    review_id: str,
    _user: dict = Depends(get_current_user),
    source_id: str | None = Query(None, description="Project source ID (optional, speeds up lookup)"),
) -> dict[str, Any]:
    """
    Retrieve a persisted code review result by its UUID.

    Issue #3716: Enables history drill-down by fetching the stored result.

    Returns the full review payload or 404 if not found/expired.
    """
    try:
        from autobot_shared.redis_client import get_redis_client

        redis = get_redis_client(async_client=False, database="analytics")
        if not redis:
            raise HTTPException(status_code=503, detail="Analytics database unavailable")

        if source_id:
            raw = await asyncio.to_thread(redis.get, f"code_review:result:{source_id}:{review_id}")
        else:
            # Scan across all sources for this review_id
            pattern = f"code_review:result:*:{review_id}"
            keys = await asyncio.to_thread(redis.keys, pattern)
            raw = await asyncio.to_thread(redis.get, keys[0]) if keys else None

        if not raw:
            raise HTTPException(status_code=404, detail=f"Review {review_id} not found or expired")

        return json.loads(raw)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to retrieve review %s: %s", review_id, exc)
        raise HTTPException(status_code=500, detail="Failed to retrieve review result")


@router.post("/review-file", response_model=CodeReviewFileResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="review_file",
    error_code_prefix="ANALYTICS_CODE_REVIEW",
)
async def review_file(
    admin_check: bool = Depends(check_admin_permission),
    file_path: str = None,
    content: str | None = None,
) -> dict[str, Any]:
    """
    Review a specific file.

    Issue #744: Requires admin authentication.

    Can accept file path or content directly.
    """
    if content is None:
        try:
            path = Path(file_path)
            # Issue #358 - avoid blocking
            if await asyncio.to_thread(path.exists):
                content = await asyncio.to_thread(path.read_text, encoding="utf-8", errors="ignore")
            else:
                raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
        except Exception:
            raise HTTPException(status_code=400, detail="Internal server error")

    comments = analyze_code(content, file_path)
    score = calculate_review_score(comments)

    return {
        "status": "success",
        "file_path": file_path,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "total_comments": len(comments),
        "score": score,
        "comments": [c.model_dump() for c in comments],
        "summary": generate_summary(comments),
    }


@router.get("/patterns", response_model=List[CodeReviewPatternItem])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_review_patterns",
    error_code_prefix="ANALYTICS_CODE_REVIEW",
)
async def get_review_patterns(
    admin_check: bool = Depends(check_admin_permission),
) -> list[dict[str, Any]]:
    """
    Get all review patterns used for analysis.

    Issue #744: Requires admin authentication.

    Returns pattern definitions with categories and severities.
    """
    return [
        {
            "id": pattern_id,
            "name": pattern_def["name"],
            "category": pattern_def["category"].value,
            "severity": pattern_def["severity"].value,
            "message": pattern_def["message"],
            "suggestion": pattern_def.get("suggestion"),
            "has_regex": pattern_def.get("pattern") is not None,
        }
        for pattern_id, pattern_def in REVIEW_PATTERNS.items()
    ]


@router.get("/history", response_model=CodeReviewHistoryResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_review_history",
    error_code_prefix="ANALYTICS_CODE_REVIEW",
)
async def get_review_history(
    admin_check: bool = Depends(check_admin_permission),
    limit: int = Query(20, ge=1, le=100),
    since: str | None = Query(None, description="ISO date string"),
    source_id: str | None = Query(None, description="Project source ID to scope analysis"),
) -> dict[str, Any]:
    """
    Get review history.

    Issue #744: Requires admin authentication.
    Issue #3441: Accepts optional source_id; validated against known sources.

    Returns past reviews for trend analysis.
    """
    await _resolve_source_or_404(source_id)

    try:
        from autobot_shared.redis_client import get_redis_client

        redis = get_redis_client(async_client=False, database="analytics")
        if not redis:
            return _no_data_response("Analytics database unavailable.")

        effective_source = source_id or "default"
        raw_entries = await asyncio.to_thread(redis.lrange, f"code_review:history:{effective_source}", 0, limit - 1)

        reviews = []
        for raw in raw_entries:
            entry = json.loads(raw)
            if since:
                try:
                    entry_dt = parse_utc_iso(entry.get("analyzed_at", ""))
                    since_dt = parse_utc_iso(since)
                    # Normalise both to UTC-aware for comparison
                    if entry_dt.tzinfo is None:
                        entry_dt = entry_dt.replace(tzinfo=timezone.utc)
                    if since_dt.tzinfo is None:
                        since_dt = since_dt.replace(tzinfo=timezone.utc)
                    if entry_dt < since_dt:
                        continue
                except ValueError:
                    pass
            reviews.append(entry)

        if not reviews:
            return _no_data_response(
                "No review history available. Reviews will be stored here once you run code reviews."
            )

        return {"status": "success", "reviews": reviews, "total": len(reviews)}
    except Exception as exc:
        logger.warning("Failed to load review history: %s", exc)
        return _no_data_response("No review history available. Reviews will be stored here once you run code reviews.")


@router.get("/metrics", response_model=CodeReviewMetricsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_review_metrics",
    error_code_prefix="ANALYTICS_CODE_REVIEW",
)
async def get_review_metrics(
    admin_check: bool = Depends(check_admin_permission),
    period: str = Query("30d", pattern="^(7d|30d|90d)$"),
    source_id: str | None = Query(None, description="Project source ID to scope analysis"),
) -> dict[str, Any]:
    """
    Get review metrics over time.

    Issue #744: Requires admin authentication.
    Issue #3441: Accepts optional source_id; validated against known sources.

    Returns aggregated statistics for trend analysis.
    """
    await _resolve_source_or_404(source_id)
    # Issue #543: Return no-data response instead of demo data
    return _no_data_response("No review metrics available. Metrics will accumulate as you run code reviews.")


@router.post("/feedback", response_model=CodeReviewFeedbackResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="submit_feedback",
    error_code_prefix="ANALYTICS_CODE_REVIEW",
)
async def submit_feedback(
    admin_check: bool = Depends(check_admin_permission),
    comment_id: str = None,
    is_helpful: bool = None,
    feedback_text: str | None = None,
) -> dict[str, Any]:
    """
    Submit feedback on a review comment.

    Issue #744: Requires admin authentication.

    Used for model improvement and learning.
    """
    try:
        from autobot_shared.redis_client import get_redis_client

        redis = get_redis_client(async_client=False, database="analytics")
        if redis:
            feedback = {
                "comment_id": comment_id,
                "is_helpful": is_helpful,
                "feedback_text": feedback_text,
                "submitted_at": datetime.now(tz=timezone.utc).isoformat(),
            }
            # Issue #361 - avoid blocking
            await asyncio.to_thread(redis.lpush, "code_review:feedback", json.dumps(feedback))
            await asyncio.to_thread(redis.ltrim, "code_review:feedback", 0, 999)  # Keep last 1000

            return {"status": "success", "feedback": feedback}
    except Exception as e:
        logger.warning("Failed to store feedback: %s", e)

    return {
        "status": "success",
        "feedback": {
            "comment_id": comment_id,
            "is_helpful": is_helpful,
        },
    }


@router.get("/summary", response_model=CodeReviewSummaryResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_review_summary",
    error_code_prefix="ANALYTICS_CODE_REVIEW",
)
async def get_review_summary(
    admin_check: bool = Depends(check_admin_permission),
    source_id: str | None = Query(None, description="Project source ID to scope analysis"),
) -> dict[str, Any]:
    """
    Get overall review system summary.

    Issue #744: Requires admin authentication.
    Issue #3441: Accepts optional source_id; validated against known sources.

    Returns dashboard-level metrics.
    """
    await _resolve_source_or_404(source_id)
    # Issue #543: Return no-data response instead of demo data
    return _no_data_response(
        "No review summary available. Summary statistics will be generated after running code reviews."
    )


@router.get("/categories", response_model=List[CodeReviewCategoryItem])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_review_categories",
    error_code_prefix="ANALYTICS_CODE_REVIEW",
)
async def get_review_categories(
    admin_check: bool = Depends(check_admin_permission),
) -> list[dict[str, Any]]:
    """
    Get all review categories with descriptions.

    Issue #744: Requires admin authentication.
    """
    return [
        {
            "id": cat.value,
            "name": cat.value.replace("_", " ").title(),
            "description": _get_category_description(cat),
            "icon": _get_category_icon(cat),
        }
        for cat in ReviewCategory
    ]


@router.post("/patterns/toggle", response_model=CodeReviewPatternToggleResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="toggle_pattern_preference",
    error_code_prefix="ANALYTICS_CODE_REVIEW",
)
async def toggle_pattern_preference(
    request: PatternToggleRequest,
    admin_check: bool = Depends(check_admin_permission),
) -> dict[str, Any]:
    """
    Toggle a code review pattern on/off.

    Issue #638: Persists pattern preferences to Redis.

    Stores user pattern preferences that persist across sessions.
    """
    try:
        from autobot_shared.redis_client import get_redis_client

        redis = get_redis_client(async_client=False, database="analytics")
        if not redis:
            raise HTTPException(status_code=503, detail="Analytics database unavailable")

        # Validate pattern exists
        if request.pattern_id not in REVIEW_PATTERNS:
            raise HTTPException(status_code=404, detail=f"Pattern {request.pattern_id} not found")

        # Store preference in Redis hash
        key = "code_review:pattern_prefs"
        await asyncio.to_thread(redis.hset, key, request.pattern_id, str(request.enabled).lower())

        logger.info("Pattern preference updated: %s = %s", request.pattern_id, request.enabled)

        return {
            "status": "success",
            "pattern_id": request.pattern_id,
            "enabled": request.enabled,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to toggle pattern preference: %s", e)
        raise HTTPException(status_code=500, detail="Failed to save preference")


@router.get("/patterns/preferences", response_model=CodeReviewPatternPreferencesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_pattern_preferences",
    error_code_prefix="ANALYTICS_CODE_REVIEW",
)
async def get_pattern_preferences(
    admin_check: bool = Depends(check_admin_permission),
) -> dict[str, Any]:
    """
    Get all pattern preferences.

    Issue #638: Retrieves pattern preferences from Redis.

    Returns user pattern preferences with all patterns enabled by default.
    """
    try:
        from autobot_shared.redis_client import get_redis_client

        redis = get_redis_client(async_client=False, database="analytics")
        if not redis:
            # Return default (all enabled) if Redis unavailable
            return {"patterns": {pattern_id: {"enabled": True} for pattern_id in REVIEW_PATTERNS.keys()}}

        # Get all preferences from Redis hash
        key = "code_review:pattern_prefs"
        prefs_raw = await asyncio.to_thread(redis.hgetall, key)

        # Build preferences dict with defaults
        patterns = {}
        for pattern_id in REVIEW_PATTERNS.keys():
            # Check if preference exists in Redis
            if pattern_id.encode() in prefs_raw:
                enabled_str = prefs_raw[pattern_id.encode()].decode()
                enabled = enabled_str.lower() == "true"
            else:
                # Default to enabled
                enabled = True

            patterns[pattern_id] = {"enabled": enabled}

        return {"patterns": patterns}
    except Exception as e:
        logger.warning("Failed to load pattern preferences: %s", e)
        # Return default (all enabled) on error
        return {"patterns": {pattern_id: {"enabled": True} for pattern_id in REVIEW_PATTERNS.keys()}}


def _get_category_description(category: ReviewCategory) -> str:
    """Get description for a category."""
    descriptions = {
        ReviewCategory.SECURITY: "Security vulnerabilities and sensitive data exposure",
        ReviewCategory.PERFORMANCE: "Performance issues and optimization opportunities",
        ReviewCategory.STYLE: "Code style and formatting issues",
        ReviewCategory.BUG_RISK: "Patterns that commonly lead to bugs",
        ReviewCategory.MAINTAINABILITY: "Code maintainability and readability issues",
        ReviewCategory.DOCUMENTATION: "Missing or incomplete documentation",
        ReviewCategory.TESTING: "Test coverage and quality issues",
        ReviewCategory.BEST_PRACTICE: "Deviations from best practices",
    }
    return descriptions.get(category, "")


def _get_category_icon(category: ReviewCategory) -> str:
    """Get icon for a category."""
    icons = {
        ReviewCategory.SECURITY: "🔒",
        ReviewCategory.PERFORMANCE: "⚡",
        ReviewCategory.STYLE: "🎨",
        ReviewCategory.BUG_RISK: "🐛",
        ReviewCategory.MAINTAINABILITY: "🔧",
        ReviewCategory.DOCUMENTATION: "📝",
        ReviewCategory.TESTING: "🧪",
        ReviewCategory.BEST_PRACTICE: "✨",
    }
    return icons.get(category, "📋")
