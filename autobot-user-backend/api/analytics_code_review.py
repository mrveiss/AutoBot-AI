# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AI-Powered Code Review Automation API (Issue #225)

Provides automated code review with pattern checking, security analysis,
and AI-generated review comments. Learns from past reviews.
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from auth_middleware import check_admin_permission
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.constants.threshold_constants import TimingConstants

logger = logging.getLogger(__name__)

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


class ReviewSeverity(str, Enum):
    """Review comment severity levels."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"
    SUGGESTION = "suggestion"


class ReviewCategory(str, Enum):
    """Categories of review findings."""

    SECURITY = "security"
    PERFORMANCE = "performance"
    STYLE = "style"
    BUG_RISK = "bug_risk"
    MAINTAINABILITY = "maintainability"
    DOCUMENTATION = "documentation"
    TESTING = "testing"
    BEST_PRACTICE = "best_practice"


class ReviewComment(BaseModel):
    """A single review comment."""

    id: str
    file_path: str
    line_number: int
    severity: ReviewSeverity
    category: ReviewCategory
    message: str
    suggestion: Optional[str] = None
    code_snippet: Optional[str] = None
    pattern_id: Optional[str] = None


class ReviewResult(BaseModel):
    """Complete review result for a diff or PR."""

    id: str
    timestamp: datetime
    files_reviewed: int
    total_comments: int
    comments: list[ReviewComment] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    score: float = Field(..., ge=0, le=100)


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
                for match in re.finditer(
                    pattern_def["pattern"], content, re.IGNORECASE | re.MULTILINE
                ):
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
            for cat, count in sorted(
                by_category.items(), key=lambda x: x[1], reverse=True
            )[:5]
        ],
    }


async def get_git_diff(commit_range: Optional[str] = None) -> str:
    """Get git diff for review."""
    try:
        cmd = ["git", "diff"]
        if commit_range:
            cmd.append(commit_range)
        else:
            cmd.append("HEAD~1..HEAD")

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=TimingConstants.SHORT_TIMEOUT
            )
            return stdout.decode("utf-8") if process.returncode == 0 else ""
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            logger.warning(
                "Git diff timed out after %s seconds", TimingConstants.SHORT_TIMEOUT
            )
            return ""
    except Exception as e:
        logger.warning("Failed to get git diff: %s", e)
        return ""


# ============================================================================
# REST Endpoints
# ============================================================================


@router.get("/analyze")
async def analyze_diff(
    admin_check: bool = Depends(check_admin_permission),
    commit_range: Optional[str] = Query(
        None, description="Git commit range (e.g., HEAD~1..HEAD)"
    ),
) -> dict[str, Any]:
    """
    Analyze git diff and generate review comments.

    Issue #744: Requires admin authentication.

    Returns review findings with severity and suggestions.
    """
    diff_content = await get_git_diff(commit_range)

    if not diff_content:
        # Issue #543: Return no-data response instead of demo data
        return _no_data_response(
            "No git diff available. Make changes or specify a commit range."
        )

    # Parse diff
    files = parse_diff(diff_content)

    # Analyze each file
    all_comments = []
    for file_info in files:
        # Get full file content for analysis
        try:
            file_path = Path(file_info["path"])
            # Issue #358 - avoid blocking
            if (
                await asyncio.to_thread(file_path.exists)
                and file_path.suffix in REVIEWABLE_EXTENSIONS
            ):
                content = await asyncio.to_thread(
                    file_path.read_text, encoding="utf-8", errors="ignore"
                )
                comments = analyze_code(content, str(file_path))
                all_comments.extend(comments)
        except Exception as e:
            logger.warning("Failed to analyze %s: %s", file_info["path"], e)

    score = calculate_review_score(all_comments)
    summary = generate_summary(all_comments)

    return {
        "status": "success",
        "id": f"review-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "timestamp": datetime.now().isoformat(),
        "files_reviewed": len(files),
        "total_comments": len(all_comments),
        "score": score,
        "comments": [c.model_dump() for c in all_comments],
        "summary": summary,
    }


@router.post("/review-file")
async def review_file(
    admin_check: bool = Depends(check_admin_permission),
    file_path: str = None,
    content: Optional[str] = None,
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
                content = await asyncio.to_thread(
                    path.read_text, encoding="utf-8", errors="ignore"
                )
            else:
                raise HTTPException(
                    status_code=404, detail=f"File not found: {file_path}"
                )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    comments = analyze_code(content, file_path)
    score = calculate_review_score(comments)

    return {
        "status": "success",
        "file_path": file_path,
        "timestamp": datetime.now().isoformat(),
        "total_comments": len(comments),
        "score": score,
        "comments": [c.model_dump() for c in comments],
        "summary": generate_summary(comments),
    }


@router.get("/patterns")
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


@router.get("/history")
async def get_review_history(
    admin_check: bool = Depends(check_admin_permission),
    limit: int = Query(20, ge=1, le=100),
    since: Optional[str] = Query(None, description="ISO date string"),
) -> dict[str, Any]:
    """
    Get review history.

    Issue #744: Requires admin authentication.

    Returns past reviews for trend analysis.
    """
    # Issue #543: Return no-data response instead of demo data
    return _no_data_response(
        "No review history available. Reviews will be stored here once you run code reviews."
    )


@router.get("/metrics")
async def get_review_metrics(
    admin_check: bool = Depends(check_admin_permission),
    period: str = Query("30d", pattern="^(7d|30d|90d)$"),
) -> dict[str, Any]:
    """
    Get review metrics over time.

    Issue #744: Requires admin authentication.

    Returns aggregated statistics for trend analysis.
    """
    # Issue #543: Return no-data response instead of demo data
    return _no_data_response(
        "No review metrics available. Metrics will accumulate as you run code reviews."
    )


@router.post("/feedback")
async def submit_feedback(
    admin_check: bool = Depends(check_admin_permission),
    comment_id: str = None,
    is_helpful: bool = None,
    feedback_text: Optional[str] = None,
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
                "submitted_at": datetime.now().isoformat(),
            }
            # Issue #361 - avoid blocking
            await asyncio.to_thread(
                redis.lpush, "code_review:feedback", json.dumps(feedback)
            )
            await asyncio.to_thread(
                redis.ltrim, "code_review:feedback", 0, 999
            )  # Keep last 1000

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


@router.get("/summary")
async def get_review_summary(
    admin_check: bool = Depends(check_admin_permission),
) -> dict[str, Any]:
    """
    Get overall review system summary.

    Issue #744: Requires admin authentication.

    Returns dashboard-level metrics.
    """
    # Issue #543: Return no-data response instead of demo data
    return _no_data_response(
        "No review summary available. Summary statistics will be generated after running code reviews."
    )


@router.get("/categories")
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


class PatternToggleRequest(BaseModel):
    """Request model for toggling pattern preference."""

    pattern_id: str
    enabled: bool


@router.post("/patterns/toggle")
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
            raise HTTPException(
                status_code=503, detail="Analytics database unavailable"
            )

        # Validate pattern exists
        if request.pattern_id not in REVIEW_PATTERNS:
            raise HTTPException(
                status_code=404, detail=f"Pattern {request.pattern_id} not found"
            )

        # Store preference in Redis hash
        key = "code_review:pattern_prefs"
        await asyncio.to_thread(
            redis.hset, key, request.pattern_id, str(request.enabled).lower()
        )

        logger.info(
            "Pattern preference updated: %s = %s", request.pattern_id, request.enabled
        )

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


@router.get("/patterns/preferences")
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
            return {
                "patterns": {
                    pattern_id: {"enabled": True}
                    for pattern_id in REVIEW_PATTERNS.keys()
                }
            }

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
        return {
            "patterns": {
                pattern_id: {"enabled": True} for pattern_id in REVIEW_PATTERNS.keys()
            }
        }


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
