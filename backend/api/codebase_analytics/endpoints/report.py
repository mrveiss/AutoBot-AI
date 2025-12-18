# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Codebase analysis report generation endpoint
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from src.utils.error_boundaries import ErrorCategory, with_error_handling

from src.utils.file_categorization import (
    FILE_CATEGORY_CODE,
    FILE_CATEGORY_BACKUP,
    FILE_CATEGORY_ARCHIVE,
    FILE_CATEGORY_DOCS,
    FILE_CATEGORY_LOGS,
    FILE_CATEGORY_CONFIG,
    FILE_CATEGORY_TEST,
    FILE_CATEGORY_DATA,
    FILE_CATEGORY_ASSETS,
    get_category_info,
)
from ..storage import get_code_collection

logger = logging.getLogger(__name__)

router = APIRouter()

# Severity order for sorting (most critical first)
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3, "hint": 4}

# All file categories for tracking
ALL_CATEGORIES = [
    FILE_CATEGORY_CODE,
    FILE_CATEGORY_CONFIG,
    FILE_CATEGORY_TEST,
    FILE_CATEGORY_BACKUP,
    FILE_CATEGORY_ARCHIVE,
    FILE_CATEGORY_DOCS,
    FILE_CATEGORY_LOGS,
    FILE_CATEGORY_DATA,
    FILE_CATEGORY_ASSETS,
]


def _get_severity_emoji(severity: str) -> str:
    """Get emoji indicator for severity level."""
    return {
        "high": "🔴",
        "medium": "🟠",
        "low": "🟡",
        "info": "🔵",
        "hint": "⚪",
    }.get(severity.lower(), "⚪")


def _format_problem_entry(problem: Dict) -> str:
    """Format a single problem as a Markdown list item."""
    file_path = problem.get("file_path", "unknown")
    line = problem.get("line_number") or problem.get("line", "?")
    description = problem.get("description", "No description")
    suggestion = problem.get("suggestion", "")

    entry = f"- **{file_path}:{line}**\n  - {description}"
    if suggestion:
        entry += f"\n  - 💡 *Suggestion: {suggestion}*"
    return entry


def _group_problems(problems: List[Dict]) -> Dict[str, Dict[str, List[Dict]]]:
    """
    Group problems by severity, then by issue type.

    Returns:
        {
            "high": {
                "race_condition": [problem1, problem2],
                "parse_error": [problem3],
            },
            "medium": {...},
            ...
        }
    """
    grouped: Dict[str, Dict[str, List[Dict]]] = {}

    for problem in problems:
        severity = problem.get("severity", "low").lower()
        issue_type = problem.get("type", "unknown")

        if severity not in grouped:
            grouped[severity] = {}
        if issue_type not in grouped[severity]:
            grouped[severity][issue_type] = []

        grouped[severity][issue_type].append(problem)

    return grouped


def _separate_by_category(problems: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Separate problems into categories (code, backup, archive, etc.).

    Returns:
        {
            "code": [problems in code files],
            "backup": [problems in backup files],
            "archive": [problems in archived files],
            ...
        }
    """
    by_category: Dict[str, List[Dict]] = {cat: [] for cat in ALL_CATEGORIES}

    for problem in problems:
        category = problem.get("file_category", FILE_CATEGORY_CODE)
        if category not in by_category:
            category = FILE_CATEGORY_CODE
        by_category[category].append(problem)

    return by_category


def _generate_category_section(
    problems: List[Dict],
    category: str,
    section_title: str,
    note: Optional[str] = None,
) -> List[str]:
    """Generate markdown section for a category of problems."""
    if not problems:
        return []

    lines = [
        f"## {section_title}",
        "",
    ]

    if note:
        lines.extend([
            f"> {note}",
            "",
        ])

    grouped = _group_problems(problems)

    for severity in ["high", "medium", "low", "info", "hint"]:
        if severity not in grouped:
            continue

        emoji = _get_severity_emoji(severity)
        severity_issues = grouped[severity]
        severity_total = sum(len(issues) for issues in severity_issues.values())

        lines.extend([
            f"### {emoji} {severity.capitalize()} Severity ({severity_total} issues)",
            "",
        ])

        for issue_type in sorted(severity_issues.keys()):
            issues = severity_issues[issue_type]
            display_type = issue_type.replace("_", " ").title()

            lines.extend([
                f"#### {display_type} ({len(issues)})",
                "",
            ])

            sorted_issues = sorted(
                issues,
                key=lambda x: (
                    x.get("file_path", ""),
                    int(x.get("line_number") or x.get("line") or 0),
                ),
            )

            for problem in sorted_issues:
                lines.append(_format_problem_entry(problem))

            lines.append("")

    return lines


def _generate_markdown_report(
    problems: List[Dict],
    analyzed_path: Optional[str] = None,
) -> str:
    """
    Generate a Markdown report from problems list.

    Problems are separated by file category:
    - Code/Config issues are shown first (priority - need to fix)
    - Backup/Archive issues shown separately (informational - may not need to fix)
    - Docs/Logs issues shown at the end (usually not critical)
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    path_info = analyzed_path or "Unknown"

    # Separate problems by category
    by_category = _separate_by_category(problems)

    # Calculate counts
    total_count = len(problems)
    code_count = (
        len(by_category[FILE_CATEGORY_CODE]) +
        len(by_category[FILE_CATEGORY_CONFIG]) +
        len(by_category[FILE_CATEGORY_TEST])
    )
    backup_count = len(by_category[FILE_CATEGORY_BACKUP])
    archive_count = len(by_category[FILE_CATEGORY_ARCHIVE])
    other_count = (
        len(by_category[FILE_CATEGORY_DOCS]) +
        len(by_category[FILE_CATEGORY_LOGS]) +
        len(by_category[FILE_CATEGORY_DATA]) +
        len(by_category[FILE_CATEGORY_ASSETS])
    )

    # Calculate severity stats for summary (all problems)
    severity_counts = {}
    type_counts = {}
    for p in problems:
        sev = p.get("severity", "low").lower()
        ptype = p.get("type", "unknown")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        type_counts[ptype] = type_counts.get(ptype, 0) + 1

    # Build report header
    lines = [
        "# Code Analysis Report",
        "",
        f"**Generated:** {now}",
        f"**Analyzed Path:** `{path_info}`",
        f"**Total Issues:** {total_count}",
        "",
        "| Category | Issues |",
        "|----------|--------|",
        f"| 📄 Code & Config | {code_count} |",
        f"| 📦 Backup Files | {backup_count} |",
        f"| 🗄️ Archived Files | {archive_count} |",
        f"| 📝 Docs & Logs | {other_count} |",
        "",
        "---",
        "",
        "## Summary",
        "",
        "### By Severity (All Files)",
        "",
        "| Severity | Count |",
        "|----------|-------|",
    ]

    for sev in ["high", "medium", "low", "info", "hint"]:
        count = severity_counts.get(sev, 0)
        if count > 0:
            emoji = _get_severity_emoji(sev)
            lines.append(f"| {emoji} {sev.capitalize()} | {count} |")

    lines.extend([
        "",
        "### By Issue Type",
        "",
        "| Issue Type | Count |",
        "|------------|-------|",
    ])

    # Sort types by count descending
    sorted_types = sorted(type_counts.items(), key=lambda x: -x[1])
    for ptype, count in sorted_types:
        display_type = ptype.replace("_", " ").title()
        lines.append(f"| {display_type} | {count} |")

    lines.extend([
        "",
        "---",
        "",
    ])

    # Section 1: Code, Config & Test Issues (PRIORITY - must fix)
    code_problems = (
        by_category[FILE_CATEGORY_CODE] +
        by_category[FILE_CATEGORY_CONFIG] +
        by_category[FILE_CATEGORY_TEST]
    )
    if code_problems:
        lines.extend(_generate_category_section(
            code_problems,
            FILE_CATEGORY_CODE,
            "📄 Code, Configuration & Test Issues",
            note="**Priority:** These issues should be fixed.",
        ))
        lines.append("---")
        lines.append("")

    # Section 2: Backup File Issues (informational)
    if by_category[FILE_CATEGORY_BACKUP]:
        lines.extend(_generate_category_section(
            by_category[FILE_CATEGORY_BACKUP],
            FILE_CATEGORY_BACKUP,
            "📦 Backup File Issues",
            note="**Note:** These are backup files kept for rollback. Fix only if restoring these files.",
        ))
        lines.append("---")
        lines.append("")

    # Section 3: Archive File Issues (informational)
    if by_category[FILE_CATEGORY_ARCHIVE]:
        lines.extend(_generate_category_section(
            by_category[FILE_CATEGORY_ARCHIVE],
            FILE_CATEGORY_ARCHIVE,
            "🗄️ Archived File Issues",
            note="**Note:** These are archived/deprecated files. Usually do not require fixes.",
        ))
        lines.append("---")
        lines.append("")

    # Section 4: Docs & Logs Issues (informational)
    docs_logs = by_category[FILE_CATEGORY_DOCS] + by_category[FILE_CATEGORY_LOGS]
    if docs_logs:
        lines.extend(_generate_category_section(
            docs_logs,
            FILE_CATEGORY_DOCS,
            "📝 Documentation & Log File Issues",
            note="**Note:** Issues in documentation or log files.",
        ))
        lines.append("---")
        lines.append("")

    # Footer
    lines.extend([
        "*Report generated by AutoBot Code Analysis*",
    ])

    return "\n".join(lines)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="generate_report",
    error_code_prefix="CODEBASE",
)
@router.get("/report")
async def generate_analysis_report(format: str = "markdown"):
    """
    Generate a code analysis report from the indexed data.

    Args:
        format: Output format (currently only 'markdown' supported)

    Returns:
        Markdown formatted report as plain text
    """
    code_collection = get_code_collection()
    problems = []

    if code_collection:
        try:
            # Fetch all problems from ChromaDB
            results = code_collection.get(
                where={"type": "problem"},
                include=["metadatas"],
            )

            if results and results.get("metadatas"):
                for metadata in results["metadatas"]:
                    problems.append({
                        "type": metadata.get("problem_type", "unknown"),
                        "severity": metadata.get("severity", "low"),
                        "file_path": metadata.get("file_path", ""),
                        "file_category": metadata.get("file_category", FILE_CATEGORY_CODE),
                        "line_number": metadata.get("line_number"),
                        "description": metadata.get("description", ""),
                        "suggestion": metadata.get("suggestion", ""),
                    })

            logger.info(f"Retrieved {len(problems)} problems for report")
        except Exception as e:
            logger.error(f"Failed to fetch problems from ChromaDB: {e}")

    if not problems:
        report = """# Code Analysis Report

**Status:** No issues found

Either no analysis has been run yet, or the codebase has no detected issues.

Run "Index Codebase" first to analyze the code.

---

*Report generated by AutoBot Code Analysis*
"""
    else:
        # Try to get the analyzed path from the latest indexing task
        # For now, we'll note it as "Indexed Codebase"
        report = _generate_markdown_report(problems, analyzed_path="Indexed Codebase")

    return PlainTextResponse(
        content=report,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="code-analysis-report.md"',
        },
    )
