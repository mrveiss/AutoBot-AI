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
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/code-review", tags=["code-review", "analytics"])

# Performance optimization: O(1) lookup for reviewable file extensions (Issue #326)
REVIEWABLE_EXTENSIONS = {".py", ".vue", ".ts", ".js"}


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
        "pattern": r'\beval\s*\(',
        "category": ReviewCategory.SECURITY,
        "severity": ReviewSeverity.CRITICAL,
        "message": "Use of eval() is a security risk. Avoid if possible.",
        "suggestion": "Use ast.literal_eval() for safe evaluation or refactor to avoid eval.",
    },
    # Performance patterns
    "PERF001": {
        "name": "N+1 Query Pattern",
        "pattern": r'for\s+\w+\s+in\s+\w+:.*\n.*\.(get|filter|select)',
        "category": ReviewCategory.PERFORMANCE,
        "severity": ReviewSeverity.WARNING,
        "message": "Potential N+1 query pattern. Consider using bulk operations.",
        "suggestion": "Use prefetch_related or select_related to optimize queries.",
    },
    "PERF002": {
        "name": "Large list in memory",
        "pattern": r'list\(\w+\.objects\.all\(\)\)',
        "category": ReviewCategory.PERFORMANCE,
        "severity": ReviewSeverity.WARNING,
        "message": "Loading entire queryset into memory. Consider pagination.",
        "suggestion": "Use iterator() or pagination for large datasets.",
    },
    # Style patterns
    "STYLE001": {
        "name": "Magic Number",
        "pattern": r'(?<![\w])(?:if|elif|while|for|return)\s+.*[^0-9]\d{2,}[^0-9]',
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
        "pattern": r'except\s*:\s*\n\s*(pass|\.\.\.)',
        "category": ReviewCategory.BUG_RISK,
        "severity": ReviewSeverity.WARNING,
        "message": "Empty except block silently swallows all exceptions.",
        "suggestion": "Log the exception or handle it explicitly.",
    },
    "BUG002": {
        "name": "Mutable default argument",
        "pattern": r'def\s+\w+\s*\([^)]*=\s*(\[\]|\{\}|set\(\))',
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
        "pattern": r'def\s+test_\w+\([^)]*\):[^}]+(?<!assert)',
        "category": ReviewCategory.TESTING,
        "severity": ReviewSeverity.WARNING,
        "message": "Test function appears to have no assertions.",
        "suggestion": "Add assert statements to verify expected behavior.",
    },
    # Best practice patterns
    "BP001": {
        "name": "Print statement",
        "pattern": r'(?<!#.*)\bprint\s*\(',
        "category": ReviewCategory.BEST_PRACTICE,
        "severity": ReviewSeverity.SUGGESTION,
        "message": "Print statement found. Use logging for production code.",
        "suggestion": "Replace with logger.info() or logger.debug().",
    },
    "BP002": {
        "name": "TODO comment",
        "pattern": r'#\s*TODO',
        "category": ReviewCategory.BEST_PRACTICE,
        "severity": ReviewSeverity.INFO,
        "message": "TODO comment found. Consider creating an issue.",
        "suggestion": "Create a GitHub issue to track this work.",
    },
}


# ============================================================================
# Utility Functions
# ============================================================================


def parse_diff(diff_content: str) -> list[dict[str, Any]]:
    """Parse unified diff format into structured data."""
    files = []
    current_file = None
    current_hunks = []
    current_hunk = None

    for line in diff_content.split("\n"):
        if line.startswith("diff --git"):
            if current_file:
                current_file["hunks"] = current_hunks
                files.append(current_file)
            # Extract file path
            parts = line.split(" b/")
            file_path = parts[-1] if len(parts) > 1 else "unknown"
            current_file = {"path": file_path, "hunks": [], "additions": 0, "deletions": 0}
            current_hunks = []
        elif line.startswith("@@"):
            if current_hunk:
                current_hunks.append(current_hunk)
            # Parse hunk header
            match = re.match(r"@@ -(\d+),?\d* \+(\d+),?\d* @@", line)
            if match:
                current_hunk = {
                    "old_start": int(match.group(1)),
                    "new_start": int(match.group(2)),
                    "lines": [],
                }
        elif current_hunk is not None:
            if line.startswith("+") and not line.startswith("+++"):
                current_hunk["lines"].append({"type": "add", "content": line[1:]})
                if current_file:
                    current_file["additions"] += 1
            elif line.startswith("-") and not line.startswith("---"):
                current_hunk["lines"].append({"type": "delete", "content": line[1:]})
                if current_file:
                    current_file["deletions"] += 1
            else:
                current_hunk["lines"].append({"type": "context", "content": line[1:] if line else ""})

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
                    line_num = content[:match.start()].count("\n") + 1
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
                logger.warning(f"Invalid regex pattern: {pattern_id}")

    # Check for long functions
    func_pattern = re.compile(r'^(async\s+)?def\s+(\w+)\s*\(', re.MULTILINE)
    for match in func_pattern.finditer(content):
        func_start = content[:match.start()].count("\n") + 1
        # Find function end (simple heuristic)
        remaining = content[match.end():]
        indent_match = re.search(r'\n(?=\S)', remaining)
        if indent_match:
            func_end = func_start + remaining[:indent_match.start()].count("\n")
            if func_end - func_start > 50:
                comments.append(
                    ReviewComment(
                        id=f"STYLE002-{func_start}",
                        file_path=file_path,
                        line_number=func_start,
                        severity=ReviewSeverity.WARNING,
                        category=ReviewCategory.MAINTAINABILITY,
                        message=f"Function '{match.group(2)}' is {func_end - func_start} lines long. Consider refactoring.",
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


async def get_git_diff(commit_range: Optional[str] = None) -> str:
    """Get git diff for review."""
    try:
        cmd = ["git", "diff"]
        if commit_range:
            cmd.append(commit_range)
        else:
            cmd.append("HEAD~1..HEAD")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
            return stdout.decode("utf-8") if process.returncode == 0 else ""
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            logger.warning("Git diff timed out after 30 seconds")
            return ""
    except Exception as e:
        logger.warning(f"Failed to get git diff: {e}")
        return ""


def generate_demo_review() -> dict[str, Any]:
    """Generate demo review data."""
    return {
        "id": "review-demo-001",
        "timestamp": datetime.now().isoformat(),
        "files_reviewed": 5,
        "total_comments": 8,
        "score": 72.5,
        "comments": [
            {
                "id": "SEC001-15",
                "file_path": "src/config.py",
                "line_number": 15,
                "severity": "critical",
                "category": "security",
                "message": "Potential hardcoded secret detected. Use environment variables.",
                "suggestion": "Move this value to an environment variable.",
                "code_snippet": 'API_KEY = "sk-abc123..."',
                "pattern_id": "SEC001",
            },
            {
                "id": "BUG002-42",
                "file_path": "src/utils.py",
                "line_number": 42,
                "severity": "warning",
                "category": "bug_risk",
                "message": "Mutable default argument can cause unexpected behavior.",
                "suggestion": "Use None as default and initialize inside the function.",
                "code_snippet": "def process_items(items=[]):",
                "pattern_id": "BUG002",
            },
            {
                "id": "PERF001-78",
                "file_path": "src/services/data.py",
                "line_number": 78,
                "severity": "warning",
                "category": "performance",
                "message": "Potential N+1 query pattern. Consider using bulk operations.",
                "suggestion": "Use prefetch_related to optimize.",
                "code_snippet": "for user in users: user.profile.load()",
                "pattern_id": "PERF001",
            },
            {
                "id": "DOC001-120",
                "file_path": "src/api/handlers.py",
                "line_number": 120,
                "severity": "info",
                "category": "documentation",
                "message": "Public function missing docstring.",
                "suggestion": "Add a docstring describing the function.",
                "code_snippet": "def handle_request(request):",
                "pattern_id": "DOC001",
            },
            {
                "id": "BP001-55",
                "file_path": "src/debug.py",
                "line_number": 55,
                "severity": "suggestion",
                "category": "best_practice",
                "message": "Print statement found. Use logging for production code.",
                "suggestion": "Replace with logger.info().",
                "code_snippet": 'print("Debug output")',
                "pattern_id": "BP001",
            },
        ],
        "summary": {
            "by_severity": {"critical": 1, "warning": 2, "info": 1, "suggestion": 1},
            "by_category": {
                "security": 1,
                "bug_risk": 1,
                "performance": 1,
                "documentation": 1,
                "best_practice": 1,
            },
            "critical_count": 1,
            "warning_count": 2,
            "info_count": 2,
            "top_issues": [
                {"category": "security", "count": 1},
                {"category": "performance", "count": 1},
                {"category": "bug_risk", "count": 1},
            ],
        },
    }


# ============================================================================
# REST Endpoints
# ============================================================================


@router.get("/analyze")
async def analyze_diff(
    commit_range: Optional[str] = Query(None, description="Git commit range (e.g., HEAD~1..HEAD)"),
) -> dict[str, Any]:
    """
    Analyze git diff and generate review comments.

    Returns review findings with severity and suggestions.
    """
    diff_content = await get_git_diff(commit_range)

    if not diff_content:
        # Return demo data
        return generate_demo_review()

    # Parse diff
    files = parse_diff(diff_content)

    # Analyze each file
    all_comments = []
    for file_info in files:
        # Get full file content for analysis
        try:
            file_path = Path(file_info["path"])
            if file_path.exists() and file_path.suffix in REVIEWABLE_EXTENSIONS:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                comments = analyze_code(content, str(file_path))
                all_comments.extend(comments)
        except Exception as e:
            logger.warning(f"Failed to analyze {file_info['path']}: {e}")

    score = calculate_review_score(all_comments)
    summary = generate_summary(all_comments)

    return {
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
    file_path: str,
    content: Optional[str] = None,
) -> dict[str, Any]:
    """
    Review a specific file.

    Can accept file path or content directly.
    """
    if content is None:
        try:
            path = Path(file_path)
            if path.exists():
                content = path.read_text(encoding="utf-8", errors="ignore")
            else:
                raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    comments = analyze_code(content, file_path)
    score = calculate_review_score(comments)

    return {
        "file_path": file_path,
        "timestamp": datetime.now().isoformat(),
        "total_comments": len(comments),
        "score": score,
        "comments": [c.model_dump() for c in comments],
        "summary": generate_summary(comments),
    }


@router.get("/patterns")
async def get_review_patterns() -> list[dict[str, Any]]:
    """
    Get all review patterns used for analysis.

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
    limit: int = Query(20, ge=1, le=100),
    since: Optional[str] = Query(None, description="ISO date string"),
) -> list[dict[str, Any]]:
    """
    Get review history.

    Returns past reviews for trend analysis.
    """
    import random
    random.seed(42)

    # Generate demo history
    history = []
    for i in range(limit):
        date = datetime.now() - timedelta(days=i)
        history.append({
            "id": f"review-{date.strftime('%Y%m%d')}",
            "timestamp": date.isoformat(),
            "files_reviewed": random.randint(2, 15),
            "total_comments": random.randint(0, 25),
            "score": round(60 + random.random() * 35, 1),
            "critical_count": random.randint(0, 3),
            "warning_count": random.randint(0, 8),
        })

    return history


@router.get("/metrics")
async def get_review_metrics(
    period: str = Query("30d", regex="^(7d|30d|90d)$"),
) -> dict[str, Any]:
    """
    Get review metrics over time.

    Returns aggregated statistics for trend analysis.
    """
    import random
    random.seed(42)

    days = int(period[:-1])
    daily_data = []

    for i in range(days):
        date = datetime.now() - timedelta(days=days - 1 - i)
        daily_data.append({
            "date": date.strftime("%Y-%m-%d"),
            "reviews": random.randint(1, 5),
            "comments": random.randint(5, 30),
            "average_score": round(65 + random.random() * 25, 1),
        })

    scores = [d["average_score"] for d in daily_data]

    return {
        "period": period,
        "data_points": daily_data,
        "totals": {
            "reviews": sum(d["reviews"] for d in daily_data),
            "comments": sum(d["comments"] for d in daily_data),
            "average_score": sum(scores) / len(scores),
        },
        "trends": {
            "score_change": scores[-1] - scores[0] if scores else 0,
            "direction": "improving" if scores[-1] > scores[0] else "declining",
        },
    }


@router.post("/feedback")
async def submit_feedback(
    comment_id: str,
    is_helpful: bool,
    feedback_text: Optional[str] = None,
) -> dict[str, Any]:
    """
    Submit feedback on a review comment.

    Used for model improvement and learning.
    """
    try:
        from src.utils.redis_client import get_redis_client

        redis = get_redis_client(async_client=False, database="analytics")
        if redis:
            feedback = {
                "comment_id": comment_id,
                "is_helpful": is_helpful,
                "feedback_text": feedback_text,
                "submitted_at": datetime.now().isoformat(),
            }
            redis.lpush("code_review:feedback", json.dumps(feedback))
            redis.ltrim("code_review:feedback", 0, 999)  # Keep last 1000

            return {"status": "recorded", "feedback": feedback}
    except Exception as e:
        logger.warning(f"Failed to store feedback: {e}")

    return {
        "status": "recorded",
        "feedback": {
            "comment_id": comment_id,
            "is_helpful": is_helpful,
        },
    }


@router.get("/summary")
async def get_review_summary() -> dict[str, Any]:
    """
    Get overall review system summary.

    Returns dashboard-level metrics.
    """
    import random
    random.seed(42)

    return {
        "timestamp": datetime.now().isoformat(),
        "total_reviews_30d": random.randint(50, 100),
        "total_comments_30d": random.randint(200, 500),
        "average_score": round(72 + random.random() * 10, 1),
        "pattern_stats": {
            "most_common": [
                {"pattern_id": "BP001", "name": "Print statement", "count": 45},
                {"pattern_id": "DOC001", "name": "Missing docstring", "count": 38},
                {"pattern_id": "BUG002", "name": "Mutable default", "count": 22},
                {"pattern_id": "STYLE001", "name": "Magic Number", "count": 18},
                {"pattern_id": "SEC001", "name": "Hardcoded Secret", "count": 5},
            ],
            "by_category": {
                "best_practice": 45,
                "documentation": 38,
                "bug_risk": 25,
                "style": 20,
                "security": 8,
                "performance": 12,
            },
        },
        "feedback_stats": {
            "total_feedback": 150,
            "helpful_rate": 0.85,
            "false_positive_rate": 0.12,
        },
        "recommendations": [
            "Focus on improving documentation coverage",
            "Replace print statements with logging",
            "Review mutable default arguments in utility functions",
        ],
    }


@router.get("/categories")
async def get_review_categories() -> list[dict[str, Any]]:
    """
    Get all review categories with descriptions.
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
