# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Codebase analysis report generation endpoint

Includes:
- Code issue analysis from ChromaDB indexed data
- Bug prediction integration (Issue #505)
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from src.utils.error_boundaries import ErrorCategory, with_error_handling
from src.code_intelligence.bug_predictor import BugPredictor, PredictionResult

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
from ..api_endpoint_scanner import APIEndpointChecker
from ..models import APIEndpointAnalysis

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


def _calculate_category_counts(by_category: Dict[str, List[Dict]]) -> Dict[str, int]:
    """Calculate issue counts by category type (Issue #398: extracted)."""
    return {
        "code": (
            len(by_category[FILE_CATEGORY_CODE]) +
            len(by_category[FILE_CATEGORY_CONFIG]) +
            len(by_category[FILE_CATEGORY_TEST])
        ),
        "backup": len(by_category[FILE_CATEGORY_BACKUP]),
        "archive": len(by_category[FILE_CATEGORY_ARCHIVE]),
        "other": (
            len(by_category[FILE_CATEGORY_DOCS]) +
            len(by_category[FILE_CATEGORY_LOGS]) +
            len(by_category[FILE_CATEGORY_DATA]) +
            len(by_category[FILE_CATEGORY_ASSETS])
        ),
    }


def _calculate_severity_and_type_counts(
    problems: List[Dict],
) -> tuple[Dict[str, int], Dict[str, int]]:
    """Calculate severity and type counts from problems (Issue #398: extracted)."""
    severity_counts: Dict[str, int] = {}
    type_counts: Dict[str, int] = {}
    for p in problems:
        sev = p.get("severity", "low").lower()
        ptype = p.get("type", "unknown")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        type_counts[ptype] = type_counts.get(ptype, 0) + 1
    return severity_counts, type_counts


def _build_report_header(
    path_info: str, total_count: int, counts: Dict[str, int]
) -> List[str]:
    """Build the report header with category counts table (Issue #398: extracted)."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return [
        "# Code Analysis Report",
        "",
        f"**Generated:** {now}",
        f"**Analyzed Path:** `{path_info}`",
        f"**Total Issues:** {total_count}",
        "",
        "| Category | Issues |",
        "|----------|--------|",
        f"| 📄 Code & Config | {counts['code']} |",
        f"| 📦 Backup Files | {counts['backup']} |",
        f"| 🗄️ Archived Files | {counts['archive']} |",
        f"| 📝 Docs & Logs | {counts['other']} |",
        "",
        "---",
        "",
    ]


def _build_summary_section(
    severity_counts: Dict[str, int], type_counts: Dict[str, int]
) -> List[str]:
    """Build the summary section with severity and type tables (Issue #398: extracted)."""
    lines = [
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

    sorted_types = sorted(type_counts.items(), key=lambda x: -x[1])
    for ptype, count in sorted_types:
        display_type = ptype.replace("_", " ").title()
        lines.append(f"| {display_type} | {count} |")

    lines.extend(["", "---", ""])
    return lines


# Risk level emoji mapping for bug prediction (Issue #505)
def _get_risk_emoji(risk_level: str) -> str:
    """Get emoji indicator for risk level."""
    return {
        "critical": "🔴",
        "high": "🟠",
        "medium": "🟡",
        "low": "🟢",
        "minimal": "🔵",
    }.get(risk_level.lower(), "⚪")


def _generate_risk_overview(prediction: PredictionResult) -> List[str]:
    """Generate bug risk overview section. Issue #484: Extracted from _generate_bug_risk_section."""
    lines = [
        "### Overview",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Files Analyzed | {prediction.analyzed_files} |",
        f"| High Risk Files | {prediction.high_risk_count} |",
        f"| Predicted Bug Locations | {prediction.predicted_bugs} |",
        "",
    ]
    return lines


def _generate_risk_distribution(prediction: PredictionResult) -> List[str]:
    """Generate risk distribution table. Issue #484: Extracted from _generate_bug_risk_section."""
    lines = ["### Risk Distribution", "", "| Risk Level | Files |", "|------------|-------|"]
    for level in ["critical", "high", "medium", "low", "minimal"]:
        count = prediction.risk_distribution.get(level, 0)
        emoji = _get_risk_emoji(level)
        lines.append(f"| {emoji} {level.capitalize()} | {count} |")
    lines.append("")
    return lines


def _generate_risk_factors(prediction: PredictionResult) -> List[str]:
    """Generate top risk factors table. Issue #484: Extracted from _generate_bug_risk_section."""
    if not prediction.top_risk_factors:
        return []
    lines = ["### Top Risk Factors", "", "| Factor | Total Score |", "|--------|-------------|"]
    for factor, score in prediction.top_risk_factors:
        display_factor = factor.replace("_", " ").title()
        lines.append(f"| {display_factor} | {score:.1f} |")
    lines.append("")
    return lines


def _generate_file_assessment_details(fa) -> List[str]:
    """Generate details for a single file assessment. Issue #484: Extracted helper."""
    lines = []
    emoji = _get_risk_emoji(fa.risk_level.value)
    lines.extend([f"#### {emoji} `{fa.file_path}` (Score: {fa.risk_score:.1f})", ""])

    if fa.factor_scores:
        top_factors = sorted(fa.factor_scores, key=lambda x: x.score, reverse=True)[:3]
        lines.append("**Contributing Factors:**")
        for fs in top_factors:
            factor_name = fs.factor.value.replace("_", " ").title()
            lines.append(f"- {factor_name}: {fs.score:.0f} ({fs.details})")
        lines.append("")

    if fa.prevention_tips:
        lines.append("**Prevention Tips:**")
        for tip in fa.prevention_tips[:3]:
            lines.append(f"- {tip}")
        lines.append("")

    if fa.recommendation:
        lines.append(f"**Recommendation:** {fa.recommendation}")
        lines.append("")

    return lines


def _generate_high_risk_files(prediction: PredictionResult) -> List[str]:
    """Generate high-risk files section. Issue #484: Extracted from _generate_bug_risk_section."""
    high_risk_files = [
        fa for fa in prediction.file_assessments
        if fa.risk_level.value in ("critical", "high")
    ][:TOP_HIGH_RISK_FILES_LIMIT]

    if not high_risk_files:
        return []

    lines = ["### High-Risk Files", "", "> Files with the highest probability of containing bugs.", ""]
    for fa in high_risk_files:
        lines.extend(_generate_file_assessment_details(fa))
    return lines


def _generate_bug_risk_section(prediction: PredictionResult) -> List[str]:
    """
    Generate the Bug Risk Analysis section for the report (Issue #505).
    Issue #484: Refactored to use extracted section builders.

    Args:
        prediction: PredictionResult from BugPredictor.analyze_directory()

    Returns:
        List of markdown lines for the bug risk section
    """
    lines = [
        "## 🐛 Bug Risk Analysis",
        "",
        "> **Predictive analysis based on code complexity, change frequency, and bug history.**",
        "",
    ]

    # Accuracy notice (Issue #468)
    if prediction.accuracy_score is not None:
        lines.append(f"**Prediction Accuracy:** {prediction.accuracy_score:.1f}%")
    else:
        lines.append("**Prediction Accuracy:** *Historical accuracy data not yet available*")
    lines.append("")

    # Compose from extracted helpers (Issue #484)
    lines.extend(_generate_risk_overview(prediction))
    lines.extend(_generate_risk_distribution(prediction))
    lines.extend(_generate_risk_factors(prediction))
    lines.extend(_generate_high_risk_files(prediction))

    lines.extend([
        "### Correlation with Detected Issues",
        "",
        "> Files appearing in both static analysis issues AND high bug risk prediction.",
        "",
        "---",
        "",
    ])

    return lines


# Maximum files to analyze for bug prediction (Issue #505)
BUG_PREDICTION_FILE_LIMIT = 100
# Timeout for bug prediction analysis (seconds)
BUG_PREDICTION_TIMEOUT = 30.0
# Maximum high-risk files to show in report
TOP_HIGH_RISK_FILES_LIMIT = 10
# Maximum items to show in API endpoint section (Issue #527)
API_ENDPOINT_LIST_LIMIT = 20


# =============================================================================
# API Endpoint Analysis Section (Issue #527)
# =============================================================================


def _get_coverage_emoji(coverage: float) -> str:
    """Get emoji indicator for coverage percentage."""
    if coverage >= 80:
        return "🟢"
    elif coverage >= 60:
        return "🟡"
    elif coverage >= 40:
        return "🟠"
    else:
        return "🔴"


def _generate_api_overview(analysis: APIEndpointAnalysis) -> List[str]:
    """Generate API endpoint overview section."""
    coverage_emoji = _get_coverage_emoji(analysis.coverage_percentage)
    lines = [
        "### Overview",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Backend Endpoints | {analysis.backend_endpoints} |",
        f"| Frontend API Calls | {analysis.frontend_calls} |",
        f"| Used Endpoints | {analysis.used_endpoints} |",
        f"| Orphaned Endpoints | {analysis.orphaned_endpoints} |",
        f"| Missing Endpoints | {analysis.missing_endpoints} |",
        f"| Coverage | {coverage_emoji} {analysis.coverage_percentage:.1f}% |",
        "",
    ]
    return lines


def _generate_orphaned_section(analysis: APIEndpointAnalysis) -> List[str]:
    """Generate orphaned endpoints section."""
    if not analysis.orphaned:
        return []

    lines = [
        "### 🔴 Orphaned Endpoints",
        "",
        "> Backend endpoints with no matching frontend calls. Consider removing if unused.",
        "",
        "| Method | Path | File | Line |",
        "|--------|------|------|------|",
    ]

    for ep in analysis.orphaned[:API_ENDPOINT_LIST_LIMIT]:
        lines.append(f"| {ep.method} | `{ep.path}` | `{ep.file_path}` | {ep.line_number} |")

    if len(analysis.orphaned) > API_ENDPOINT_LIST_LIMIT:
        lines.append(f"| ... | *{len(analysis.orphaned) - API_ENDPOINT_LIST_LIMIT} more* | | |")

    lines.append("")
    return lines


def _generate_missing_section(analysis: APIEndpointAnalysis) -> List[str]:
    """Generate missing endpoints section."""
    if not analysis.missing:
        return []

    lines = [
        "### 🟠 Missing Endpoints",
        "",
        "> Frontend API calls with no matching backend endpoint. May indicate bugs or deprecated usage.",
        "",
        "| Method | Path | Called From | Line |",
        "|--------|------|-------------|------|",
    ]

    for ep in analysis.missing[:API_ENDPOINT_LIST_LIMIT]:
        lines.append(f"| {ep.method} | `{ep.path}` | `{ep.file_path}` | {ep.line_number} |")

    if len(analysis.missing) > API_ENDPOINT_LIST_LIMIT:
        lines.append(f"| ... | *{len(analysis.missing) - API_ENDPOINT_LIST_LIMIT} more* | | |")

    lines.append("")
    return lines


def _generate_most_used_section(analysis: APIEndpointAnalysis) -> List[str]:
    """Generate most used endpoints section."""
    if not analysis.used:
        return []

    # Sort by call count
    sorted_used = sorted(analysis.used, key=lambda x: x.call_count, reverse=True)

    lines = [
        "### 🟢 Most Used Endpoints",
        "",
        "| Method | Path | Call Count |",
        "|--------|------|------------|",
    ]

    for usage in sorted_used[:10]:
        ep = usage.endpoint
        lines.append(f"| {ep.method} | `{ep.path}` | {usage.call_count} |")

    lines.append("")
    return lines


def _generate_api_endpoint_section(analysis: Optional[APIEndpointAnalysis]) -> List[str]:
    """
    Generate the API Endpoint Analysis section for the report (Issue #527).

    Args:
        analysis: APIEndpointAnalysis from APIEndpointChecker

    Returns:
        List of markdown lines for the API endpoint section
    """
    if not analysis:
        return []

    lines = [
        "## 🔌 API Endpoint Analysis",
        "",
        "> **Cross-reference analysis of backend endpoints and frontend API calls.**",
        "",
    ]

    lines.extend(_generate_api_overview(analysis))
    lines.extend(_generate_orphaned_section(analysis))
    lines.extend(_generate_missing_section(analysis))
    lines.extend(_generate_most_used_section(analysis))

    lines.extend(["---", ""])

    return lines


async def _get_api_endpoint_analysis() -> Optional[APIEndpointAnalysis]:
    """
    Get API endpoint analysis for the project (Issue #527).

    Returns:
        APIEndpointAnalysis or None if analysis fails
    """
    try:
        checker = APIEndpointChecker()
        analysis = checker.run_full_analysis()
        logger.info(
            "API endpoint analysis: %d endpoints, %d calls, %.1f%% coverage",
            analysis.backend_endpoints,
            analysis.frontend_calls,
            analysis.coverage_percentage,
        )
        return analysis
    except Exception as e:
        logger.error("API endpoint analysis failed: %s", e, exc_info=True)
        return None


async def _get_bug_prediction(
    project_root: Optional[str] = None,
    limit: int = BUG_PREDICTION_FILE_LIMIT,
) -> Optional[PredictionResult]:
    """
    Get bug prediction data for the project (Issue #505).

    Runs the analysis in a thread pool to avoid blocking the async event loop.

    Args:
        project_root: Root directory to analyze (defaults to current directory)
        limit: Maximum number of files to analyze

    Returns:
        PredictionResult or None if analysis fails or times out
    """
    try:
        # Use project root or default to current working directory
        root = project_root or str(Path.cwd())

        # Run in thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        predictor = BugPredictor(project_root=root)

        result = await asyncio.wait_for(
            loop.run_in_executor(
                None,  # Use default thread pool
                lambda: predictor.analyze_directory(pattern="*.py", limit=limit),
            ),
            timeout=BUG_PREDICTION_TIMEOUT,
        )

        logger.info(
            "Bug prediction completed: %s files analyzed, %s high-risk",
            result.analyzed_files,
            result.high_risk_count,
        )
        return result

    except asyncio.TimeoutError:
        logger.warning(
            "Bug prediction timed out after %ss", BUG_PREDICTION_TIMEOUT
        )
        return None
    except FileNotFoundError as e:
        logger.warning("Project root not found for bug prediction: %s", e)
        return None
    except Exception as e:
        logger.error("Bug prediction analysis failed: %s", e, exc_info=True)
        return None


def _build_issue_sections(by_category: Dict[str, List[Dict]]) -> List[str]:
    """Build all issue category sections (Issue #398: extracted)."""
    lines = []

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
        lines.extend(["---", ""])

    # Section 2: Backup File Issues (informational)
    if by_category[FILE_CATEGORY_BACKUP]:
        lines.extend(_generate_category_section(
            by_category[FILE_CATEGORY_BACKUP],
            FILE_CATEGORY_BACKUP,
            "📦 Backup File Issues",
            note="**Note:** These are backup files kept for rollback. "
                 "Fix only if restoring these files.",
        ))
        lines.extend(["---", ""])

    # Section 3: Archive File Issues (informational)
    if by_category[FILE_CATEGORY_ARCHIVE]:
        lines.extend(_generate_category_section(
            by_category[FILE_CATEGORY_ARCHIVE],
            FILE_CATEGORY_ARCHIVE,
            "🗄️ Archived File Issues",
            note="**Note:** These are archived/deprecated files. "
                 "Usually do not require fixes.",
        ))
        lines.extend(["---", ""])

    # Section 4: Docs & Logs Issues (informational)
    docs_logs = by_category[FILE_CATEGORY_DOCS] + by_category[FILE_CATEGORY_LOGS]
    if docs_logs:
        lines.extend(_generate_category_section(
            docs_logs,
            FILE_CATEGORY_DOCS,
            "📝 Documentation & Log File Issues",
            note="**Note:** Issues in documentation or log files.",
        ))
        lines.extend(["---", ""])

    return lines


def _build_correlation_section(
    problems: List[Dict],
    prediction: Optional[PredictionResult],
) -> List[str]:
    """
    Build cross-reference section showing files with both issues AND high risk (Issue #505).

    Args:
        problems: List of detected code issues
        prediction: Bug prediction result

    Returns:
        List of markdown lines for correlation section
    """
    if not prediction:
        return []

    lines = []

    # Get files with issues
    files_with_issues = set(p.get("file_path", "") for p in problems if p.get("file_path"))

    # Get high-risk files
    high_risk_files = {
        fa.file_path: fa
        for fa in prediction.file_assessments
        if fa.risk_level.value in ("critical", "high")
    }

    # Find overlap
    overlap = files_with_issues & set(high_risk_files.keys())

    if overlap:
        lines.extend([
            "**⚠️ Priority Files (Issues + High Bug Risk):**",
            "",
            "| File | Issue Count | Risk Score | Risk Level |",
            "|------|-------------|------------|------------|",
        ])

        # Count issues per file
        issue_counts: Dict[str, int] = {}
        for p in problems:
            fp = p.get("file_path", "")
            if fp in overlap:
                issue_counts[fp] = issue_counts.get(fp, 0) + 1

        # Sort by risk score
        sorted_overlap = sorted(
            overlap,
            key=lambda f: high_risk_files[f].risk_score,
            reverse=True,
        )

        for file_path in sorted_overlap[:10]:
            fa = high_risk_files[file_path]
            issue_count = issue_counts.get(file_path, 0)
            emoji = _get_risk_emoji(fa.risk_level.value)
            lines.append(
                f"| `{file_path}` | {issue_count} | {fa.risk_score:.1f} | "
                f"{emoji} {fa.risk_level.value.capitalize()} |"
            )

        lines.extend([
            "",
            f"> **{len(overlap)} files** have both detected issues and high bug risk. "
            "These should be prioritized for review.",
            "",
        ])
    else:
        lines.append("*No files appear in both static analysis issues and high bug risk.*")
        lines.append("")

    return lines


def _generate_markdown_report(
    problems: List[Dict],
    analyzed_path: Optional[str] = None,
    bug_prediction: Optional[PredictionResult] = None,
    api_endpoint_analysis: Optional[APIEndpointAnalysis] = None,
) -> str:
    """
    Generate a Markdown report from problems list (Issue #398: refactored, Issue #505: bug prediction).

    Problems are separated by file category:
    - Code/Config issues are shown first (priority - need to fix)
    - Backup/Archive issues shown separately (informational - may not need to fix)
    - Docs/Logs issues shown at the end (usually not critical)

    Bug prediction section added (Issue #505):
    - High-risk files summary
    - Risk distribution
    - Correlation with detected issues

    API endpoint analysis added (Issue #527):
    - Endpoint coverage
    - Orphaned endpoints
    - Missing endpoints
    """
    path_info = analyzed_path or "Unknown"
    by_category = _separate_by_category(problems)

    # Calculate statistics
    counts = _calculate_category_counts(by_category)
    severity_counts, type_counts = _calculate_severity_and_type_counts(problems)

    # Build report sections
    lines = _build_report_header(path_info, len(problems), counts)
    lines.extend(_build_summary_section(severity_counts, type_counts))

    # Add API endpoint analysis section (Issue #527)
    if api_endpoint_analysis:
        lines.extend(_generate_api_endpoint_section(api_endpoint_analysis))

    # Add bug risk section if prediction available (Issue #505)
    if bug_prediction:
        bug_risk_lines = _generate_bug_risk_section(bug_prediction)
        # Insert correlation data into the bug risk section
        correlation_lines = _build_correlation_section(problems, bug_prediction)
        # Find where to insert correlation (before the final ---)
        if correlation_lines:
            # Replace placeholder correlation section
            insert_idx = None
            for i, line in enumerate(bug_risk_lines):
                if line == "### Correlation with Detected Issues":
                    insert_idx = i
                    break
            if insert_idx is not None:
                # Remove placeholder and insert real data
                bug_risk_lines = (
                    bug_risk_lines[:insert_idx + 3] +  # Keep header + blank + note
                    correlation_lines +
                    bug_risk_lines[-2:]  # Keep final --- and blank
                )
        lines.extend(bug_risk_lines)

    lines.extend(_build_issue_sections(by_category))
    lines.append("*Report generated by AutoBot Code Analysis*")

    return "\n".join(lines)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="generate_report",
    error_code_prefix="CODEBASE",
)
@router.get("/report")
async def generate_analysis_report(
    format: str = "markdown",
    include_api_analysis: bool = True,
):
    """
    Generate a code analysis report from the indexed data.

    Args:
        format: Output format (currently only 'markdown' supported)
        include_api_analysis: Whether to include API endpoint analysis (Issue #527)

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

            logger.info("Retrieved %s problems for report", len(problems))
        except Exception as e:
            logger.error("Failed to fetch problems from ChromaDB: %s", e)

    # Get bug prediction data (Issue #505)
    bug_prediction = await _get_bug_prediction()

    # Get API endpoint analysis (Issue #527)
    api_endpoint_analysis = None
    if include_api_analysis:
        api_endpoint_analysis = await _get_api_endpoint_analysis()

    if not problems:
        # Even with no issues, include other analyses if available
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            "# Code Analysis Report",
            "",
            f"**Generated:** {now}",
            "**Status:** No code issues detected",
            "",
            "> No static analysis issues found.",
            "",
            "---",
            "",
        ]

        # Add API endpoint analysis even with no code issues (Issue #527)
        if api_endpoint_analysis:
            lines.extend(_generate_api_endpoint_section(api_endpoint_analysis))

        # Add bug prediction if available (Issue #505)
        if bug_prediction and bug_prediction.analyzed_files > 0:
            lines.extend(_generate_bug_risk_section(bug_prediction))

        if not api_endpoint_analysis and (not bug_prediction or bug_prediction.analyzed_files == 0):
            lines.append("Run \"Index Codebase\" first to analyze the code.")
            lines.append("")

        lines.append("*Report generated by AutoBot Code Analysis*")
        report = "\n".join(lines)
    else:
        # Try to get the analyzed path from the latest indexing task
        # For now, we'll note it as "Indexed Codebase"
        report = _generate_markdown_report(
            problems,
            analyzed_path="Indexed Codebase",
            bug_prediction=bug_prediction,
            api_endpoint_analysis=api_endpoint_analysis,
        )

    return PlainTextResponse(
        content=report,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="code-analysis-report.md"',
        },
    )
