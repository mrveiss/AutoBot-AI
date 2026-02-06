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
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from code_intelligence.bug_predictor import BugPredictor, PredictionResult

# Issue #244: Cross-Language Pattern Detection
from code_intelligence.cross_language_patterns import (
    CrossLanguageAnalysis,
    CrossLanguagePatternDetector,
)

# Issue #208: Code Pattern Detection & Optimization
from code_intelligence.pattern_analysis import (
    CodePatternAnalyzer,
    PatternAnalysisReport,
)
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from utils.file_categorization import (
    FILE_CATEGORY_ARCHIVE,
    FILE_CATEGORY_ASSETS,
    FILE_CATEGORY_BACKUP,
    FILE_CATEGORY_CODE,
    FILE_CATEGORY_CONFIG,
    FILE_CATEGORY_DATA,
    FILE_CATEGORY_DOCS,
    FILE_CATEGORY_LOGS,
    FILE_CATEGORY_TEST,
)

from ..api_endpoint_scanner import APIEndpointChecker
from ..duplicate_detector import DuplicateAnalysis, DuplicateCodeDetector  # noqa: F401
from ..models import APIEndpointAnalysis
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


def _format_issue_type_subsection(issue_type: str, issues: List[Dict]) -> List[str]:
    """
    Format a single issue type subsection with sorted issues.

    Issue #620: Extracted from _generate_category_section.
    """
    display_type = issue_type.replace("_", " ").title()
    lines = [f"#### {display_type} ({len(issues)})", ""]

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


def _format_severity_subsection(
    severity: str, severity_issues: Dict[str, List[Dict]]
) -> List[str]:
    """
    Format a severity subsection with all its issue types.

    Issue #620: Extracted from _generate_category_section.
    """
    emoji = _get_severity_emoji(severity)
    severity_total = sum(len(issues) for issues in severity_issues.values())

    lines = [
        f"### {emoji} {severity.capitalize()} Severity ({severity_total} issues)",
        "",
    ]

    for issue_type in sorted(severity_issues.keys()):
        lines.extend(
            _format_issue_type_subsection(issue_type, severity_issues[issue_type])
        )

    return lines


def _generate_category_section(
    problems: List[Dict],
    category: str,
    section_title: str,
    note: Optional[str] = None,
) -> List[str]:
    """
    Generate markdown section for a category of problems.

    Issue #620: Refactored to use extracted helpers.
    """
    if not problems:
        return []

    lines = [f"## {section_title}", ""]
    if note:
        lines.extend([f"> {note}", ""])

    grouped = _group_problems(problems)

    for severity in ["high", "medium", "low", "info", "hint"]:
        if severity in grouped:
            lines.extend(_format_severity_subsection(severity, grouped[severity]))

    return lines


def _calculate_category_counts(by_category: Dict[str, List[Dict]]) -> Dict[str, int]:
    """Calculate issue counts by category type (Issue #398: extracted)."""
    return {
        "code": (
            len(by_category[FILE_CATEGORY_CODE])
            + len(by_category[FILE_CATEGORY_CONFIG])
            + len(by_category[FILE_CATEGORY_TEST])
        ),
        "backup": len(by_category[FILE_CATEGORY_BACKUP]),
        "archive": len(by_category[FILE_CATEGORY_ARCHIVE]),
        "other": (
            len(by_category[FILE_CATEGORY_DOCS])
            + len(by_category[FILE_CATEGORY_LOGS])
            + len(by_category[FILE_CATEGORY_DATA])
            + len(by_category[FILE_CATEGORY_ASSETS])
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

    lines.extend(
        [
            "",
            "### By Issue Type",
            "",
            "| Issue Type | Count |",
            "|------------|-------|",
        ]
    )

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
    lines = [
        "### Risk Distribution",
        "",
        "| Risk Level | Files |",
        "|------------|-------|",
    ]
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
    lines = [
        "### Top Risk Factors",
        "",
        "| Factor | Total Score |",
        "|--------|-------------|",
    ]
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
        fa
        for fa in prediction.file_assessments
        if fa.risk_level.value in ("critical", "high")
    ][:TOP_HIGH_RISK_FILES_LIMIT]

    if not high_risk_files:
        return []

    lines = [
        "### High-Risk Files",
        "",
        "> Files with the highest probability of containing bugs.",
        "",
    ]
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
        lines.append(
            "**Prediction Accuracy:** *Historical accuracy data not yet available*"
        )
    lines.append("")

    # Compose from extracted helpers (Issue #484)
    lines.extend(_generate_risk_overview(prediction))
    lines.extend(_generate_risk_distribution(prediction))
    lines.extend(_generate_risk_factors(prediction))
    lines.extend(_generate_high_risk_files(prediction))

    lines.extend(
        [
            "### Correlation with Detected Issues",
            "",
            "> Files appearing in both static analysis issues AND high bug risk prediction.",
            "",
            "---",
            "",
        ]
    )

    return lines


# Import from SSOT configuration (Issue #554)
from constants.threshold_constants import AnalyticsConfig

# Maximum files to analyze for bug prediction - from SSOT
BUG_PREDICTION_FILE_LIMIT = AnalyticsConfig.BUG_PREDICTION_FILE_LIMIT
# Timeout for bug prediction analysis (seconds) - from SSOT
BUG_PREDICTION_TIMEOUT = AnalyticsConfig.BUG_PREDICTION_TIMEOUT
# Maximum high-risk files to show in report - from SSOT
TOP_HIGH_RISK_FILES_LIMIT = AnalyticsConfig.TOP_HIGH_RISK_FILES_LIMIT
# Maximum items to show in API endpoint section - from SSOT
API_ENDPOINT_LIST_LIMIT = AnalyticsConfig.API_ENDPOINT_LIST_LIMIT


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
        lines.append(
            f"| {ep.method} | `{ep.path}` | `{ep.file_path}` | {ep.line_number} |"
        )

    if len(analysis.orphaned) > API_ENDPOINT_LIST_LIMIT:
        lines.append(
            f"| ... | *{len(analysis.orphaned) - API_ENDPOINT_LIST_LIMIT} more* | | |"
        )

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
        lines.append(
            f"| {ep.method} | `{ep.path}` | `{ep.file_path}` | {ep.line_number} |"
        )

    if len(analysis.missing) > API_ENDPOINT_LIST_LIMIT:
        lines.append(
            f"| ... | *{len(analysis.missing) - API_ENDPOINT_LIST_LIMIT} more* | | |"
        )

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


def _generate_api_endpoint_section(
    analysis: Optional[APIEndpointAnalysis],
) -> List[str]:
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


# =============================================================================
# Duplicate Code Analysis Section (Issue #528)
# =============================================================================


def _get_similarity_emoji(similarity: float) -> str:
    """Get emoji indicator for similarity percentage."""
    if similarity >= 90:
        return "🔴"  # High similarity - exact or near-exact
    elif similarity >= 70:
        return "🟠"  # Medium similarity
    else:
        return "🟡"  # Low similarity


def _generate_duplicate_overview(analysis: DuplicateAnalysis) -> List[str]:
    """Generate duplicate code overview section."""
    lines = [
        "### Overview",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Files Analyzed | {analysis.files_analyzed} |",
        f"| Total Duplicate Pairs | {analysis.total_duplicates} |",
        f"| High Similarity (90%+) | {analysis.high_similarity_count} |",
        f"| Medium Similarity (70-89%) | {analysis.medium_similarity_count} |",
        f"| Low Similarity (50-69%) | {analysis.low_similarity_count} |",
        f"| Total Duplicate Lines | {analysis.total_duplicate_lines} |",
        "",
    ]
    return lines


def _generate_high_similarity_duplicates(analysis: DuplicateAnalysis) -> List[str]:
    """Generate high similarity duplicates section."""
    high_similarity_dups = [d for d in analysis.duplicates if d.similarity >= 0.90]
    if not high_similarity_dups:
        return []

    lines = [
        "### 🔴 High Similarity Duplicates (90%+)",
        "",
        "> These are exact or near-exact duplicates. Consider extracting to shared utility.",
        "",
        "| File 1 | Lines | File 2 | Lines | Similarity |",
        "|--------|-------|--------|-------|------------|",
    ]

    for dup in high_similarity_dups[:15]:  # Limit to top 15
        file1_short = _shorten_path(dup.file1)
        file2_short = _shorten_path(dup.file2)
        lines.append(
            f"| `{file1_short}` | {dup.start_line1}-{dup.end_line1} | "
            f"`{file2_short}` | {dup.start_line2}-{dup.end_line2} | "
            f"{dup.similarity * 100:.0f}% |"
        )

    if len(high_similarity_dups) > 15:
        lines.append(f"| ... | *{len(high_similarity_dups) - 15} more* | | | |")

    lines.append("")
    return lines


def _generate_medium_similarity_duplicates(analysis: DuplicateAnalysis) -> List[str]:
    """Generate medium similarity duplicates section."""
    medium_similarity_dups = [
        d for d in analysis.duplicates if 0.70 <= d.similarity < 0.90
    ]
    if not medium_similarity_dups:
        return []

    lines = [
        "### 🟠 Medium Similarity Duplicates (70-89%)",
        "",
        "> Similar patterns that may benefit from consolidation.",
        "",
        "| File 1 | File 2 | Similarity | Lines |",
        "|--------|--------|------------|-------|",
    ]

    for dup in medium_similarity_dups[:10]:  # Limit to top 10
        file1_short = _shorten_path(dup.file1)
        file2_short = _shorten_path(dup.file2)
        lines.append(
            f"| `{file1_short}` | `{file2_short}` | "
            f"{dup.similarity * 100:.0f}% | {dup.line_count} |"
        )

    if len(medium_similarity_dups) > 10:
        lines.append(f"| ... | *{len(medium_similarity_dups) - 10} more* | | |")

    lines.append("")
    return lines


def _shorten_path(path: str, max_length: int = 50) -> str:
    """Shorten a file path for table display."""
    if len(path) <= max_length:
        return path
    # Keep the last portion
    parts = path.split("/")
    if len(parts) > 2:
        return f".../{parts[-2]}/{parts[-1]}"
    return path[-max_length:]


def _generate_duplicate_code_section(
    analysis: Optional[DuplicateAnalysis],
) -> List[str]:
    """
    Generate the Duplicate Code Analysis section for the report (Issue #528).

    Args:
        analysis: DuplicateAnalysis from DuplicateCodeDetector

    Returns:
        List of markdown lines for the duplicate code section
    """
    if not analysis or analysis.total_duplicates == 0:
        return []

    lines = [
        "## 📋 Duplicate Code Analysis",
        "",
        "> **Detection of duplicate code blocks across the codebase.**",
        "",
    ]

    lines.extend(_generate_duplicate_overview(analysis))
    lines.extend(_generate_high_similarity_duplicates(analysis))
    lines.extend(_generate_medium_similarity_duplicates(analysis))

    # Add recommendations if high duplicates found
    if analysis.high_similarity_count > 0:
        lines.extend(
            [
                "### Recommendations",
                "",
                "- **Extract common code** to shared utilities or base classes",
                "- **Review high-similarity pairs** for potential consolidation",
                "- **Consider design patterns** like Template Method or Strategy for similar logic",
                "",
            ]
        )

    lines.extend(["---", ""])

    return lines


# =============================================================================
# Cross-Language Pattern Analysis Section (Issue #244)
# =============================================================================


def _get_severity_color(severity: str) -> str:
    """Get color indicator for severity level."""
    return {
        "critical": "🔴",
        "high": "🟠",
        "medium": "🟡",
        "low": "🟢",
        "info": "🔵",
    }.get(severity.lower(), "⚪")


def _generate_cross_language_overview(analysis: CrossLanguageAnalysis) -> List[str]:
    """Generate cross-language analysis overview section."""
    total_files = (
        analysis.python_files_analyzed
        + analysis.typescript_files_analyzed
        + analysis.vue_files_analyzed
    )

    lines = [
        "### Overview",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Python Files | {analysis.python_files_analyzed} |",
        f"| TypeScript Files | {analysis.typescript_files_analyzed} |",
        f"| Vue Files | {analysis.vue_files_analyzed} |",
        f"| Total Files | {total_files} |",
        f"| Patterns Detected | {analysis.total_patterns} |",
        f"| DTO Mismatches | {len(analysis.dto_mismatches)} |",
        f"| API Mismatches | {len(analysis.api_contract_mismatches)} |",
        f"| Validation Duplications | {len(analysis.validation_duplications)} |",
        f"| Semantic Matches | {len(analysis.pattern_matches)} |",
        "",
    ]
    return lines


def _generate_dto_mismatches_section(analysis: CrossLanguageAnalysis) -> List[str]:
    """Generate DTO mismatches section for report."""
    if not analysis.dto_mismatches:
        return []

    lines = [
        "### 🔴 DTO/Type Mismatches",
        "",
        "> Fields or types that differ between Python models and TypeScript interfaces.",
        "",
        "| Type | Field | Mismatch | Recommendation |",
        "|------|-------|----------|----------------|",
    ]

    for m in analysis.dto_mismatches[:15]:
        lines.append(
            f"| `{m.backend_type}` | `{m.field_name}` | {m.mismatch_type} | {m.recommendation[:50]}... |"
        )

    if len(analysis.dto_mismatches) > 15:
        lines.append(f"| ... | *{len(analysis.dto_mismatches) - 15} more* | | |")

    lines.append("")
    return lines


def _generate_api_mismatches_section(analysis: CrossLanguageAnalysis) -> List[str]:
    """Generate API contract mismatches section for report."""
    if not analysis.api_contract_mismatches:
        return []

    orphaned = [
        m
        for m in analysis.api_contract_mismatches
        if m.mismatch_type == "orphaned_endpoint"
    ]
    missing = [
        m
        for m in analysis.api_contract_mismatches
        if m.mismatch_type == "missing_endpoint"
    ]

    lines = [
        "### 🟠 API Contract Mismatches",
        "",
    ]

    if missing:
        lines.extend(
            [
                "#### Missing Endpoints (Called but not defined)",
                "",
                "> Frontend calls endpoints that don't exist in the backend.",
                "",
                "| Method | Path | Called From |",
                "|--------|------|-------------|",
            ]
        )
        for m in missing[:10]:
            loc = m.frontend_location
            file_info = f"`{loc.file_path}:{loc.line_start}`" if loc else "Unknown"
            lines.append(f"| {m.http_method} | `{m.endpoint_path}` | {file_info} |")
        if len(missing) > 10:
            lines.append(f"| ... | *{len(missing) - 10} more* | |")
        lines.append("")

    if orphaned:
        lines.extend(
            [
                "#### Orphaned Endpoints (Defined but not called)",
                "",
                "> Backend endpoints with no frontend usage.",
                "",
                "| Method | Path | Defined In |",
                "|--------|------|------------|",
            ]
        )
        for m in orphaned[:10]:
            loc = m.backend_location
            file_info = f"`{loc.file_path}:{loc.line_start}`" if loc else "Unknown"
            lines.append(f"| {m.http_method} | `{m.endpoint_path}` | {file_info} |")
        if len(orphaned) > 10:
            lines.append(f"| ... | *{len(orphaned) - 10} more* | |")
        lines.append("")

    return lines


def _generate_validation_duplications_section(
    analysis: CrossLanguageAnalysis,
) -> List[str]:
    """Generate validation duplications section for report."""
    if not analysis.validation_duplications:
        return []

    lines = [
        "### 🟡 Validation Logic Duplications",
        "",
        "> Same validation rules implemented in both Python and TypeScript.",
        "",
        "| Validation Type | Python Location | TypeScript Location |",
        "|-----------------|-----------------|---------------------|",
    ]

    for v in analysis.validation_duplications[:10]:
        py_loc = (
            f"`{v.python_location.file_path}:{v.python_location.line_start}`"
            if v.python_location
            else "N/A"
        )
        ts_loc = (
            f"`{v.typescript_location.file_path}:{v.typescript_location.line_start}`"
            if v.typescript_location
            else "N/A"
        )
        lines.append(f"| {v.validation_type} | {py_loc} | {ts_loc} |")

    if len(analysis.validation_duplications) > 10:
        lines.append(f"| ... | *{len(analysis.validation_duplications) - 10} more* | |")

    lines.extend(
        [
            "",
            "**Recommendation:** Consider using a shared validation schema "
            "(e.g., JSON Schema, Zod) to ensure consistency.",
            "",
        ]
    )

    return lines


def _generate_semantic_matches_section(analysis: CrossLanguageAnalysis) -> List[str]:
    """Generate semantic pattern matches section for report."""
    if not analysis.pattern_matches:
        return []

    # Filter high-similarity matches
    high_similarity = [m for m in analysis.pattern_matches if m.similarity_score >= 0.8]

    if not high_similarity:
        return []

    lines = [
        "### 🔵 Semantic Pattern Matches",
        "",
        "> Similar code patterns detected across Python and TypeScript using AI embeddings.",
        "",
        "| Similarity | Python Pattern | TypeScript Pattern |",
        "|------------|----------------|-------------------|",
    ]

    for m in high_similarity[:10]:
        py_name = m.metadata.get("python_name", "Unknown") if m.metadata else "Unknown"
        ts_name = (
            m.metadata.get("typescript_name", "Unknown") if m.metadata else "Unknown"
        )
        lines.append(f"| {m.similarity_score:.0%} | `{py_name}` | `{ts_name}` |")

    if len(high_similarity) > 10:
        lines.append(f"| ... | *{len(high_similarity) - 10} more* | |")

    lines.extend(
        [
            "",
            "**Note:** High semantic similarity may indicate duplicated business logic that could be consolidated.",
            "",
        ]
    )

    return lines


def _generate_pattern_overview(report: PatternAnalysisReport) -> List[str]:
    """Generate pattern analysis overview table (Issue #560: extracted)."""
    return [
        "### Overview",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Patterns Found | {report.total_patterns} |",
        f"| Files Analyzed | {report.files_analyzed} |",
        f"| Lines Analyzed | {report.lines_analyzed} |",
        f"| Potential LOC Reduction | {report.potential_loc_reduction} |",
        f"| Analysis Duration | {report.analysis_duration_seconds:.1f}s |",
        "",
    ]


def _generate_severity_distribution(report: PatternAnalysisReport) -> List[str]:
    """Generate severity distribution section (Issue #560: extracted)."""
    if not report.severity_distribution:
        return []

    lines = [
        "### Severity Distribution",
        "",
        "| Severity | Count |",
        "|----------|-------|",
    ]
    severity_emojis = {
        "critical": "🔴",
        "high": "🟠",
        "medium": "🟡",
        "low": "🟢",
        "info": "🔵",
    }
    for severity in ["critical", "high", "medium", "low", "info"]:
        count = report.severity_distribution.get(severity, 0)
        if count > 0:
            emoji = severity_emojis.get(severity, "⚪")
            lines.append(f"| {emoji} {severity.capitalize()} | {count} |")
    lines.append("")
    return lines


def _generate_duplicate_patterns_section(report: PatternAnalysisReport) -> List[str]:
    """Generate duplicate code patterns section (Issue #560: extracted)."""
    if not report.duplicate_patterns:
        return []

    lines = [
        "### 📋 Duplicate Code Patterns",
        "",
        f"> **{len(report.duplicate_patterns)} duplicate patterns detected**",
        "",
    ]
    for i, dup in enumerate(report.duplicate_patterns[:10], 1):  # Limit to 10
        severity_emoji = {"high": "🔴", "medium": "🟠", "low": "🟡"}.get(
            dup.severity.value if hasattr(dup.severity, "value") else str(dup.severity),
            "⚪",
        )
        lines.extend(
            [
                f"#### {i}. {severity_emoji} {dup.description}",
                f"- **Similarity:** {dup.similarity_score:.1%}",
                f"- **Code Reduction:** ~{dup.code_reduction_potential} lines",
                f"- **Locations:** {len(dup.locations)} occurrences",
                f"- **Suggestion:** {dup.suggestion}",
                "",
            ]
        )
    if len(report.duplicate_patterns) > 10:
        lines.append(f"*... and {len(report.duplicate_patterns) - 10} more duplicates*")
        lines.append("")
    return lines


def _generate_regex_opportunities_section(report: PatternAnalysisReport) -> List[str]:
    """Generate regex optimization opportunities section (Issue #560: extracted)."""
    if not report.regex_opportunities:
        return []

    lines = [
        "### ⚡ Regex Optimization Opportunities",
        "",
        f"> **{len(report.regex_opportunities)} opportunities for regex optimization**",
        "",
    ]
    for i, regex_opp in enumerate(report.regex_opportunities[:5], 1):  # Limit to 5
        suggested = regex_opp.suggested_regex[:80]
        if len(regex_opp.suggested_regex) > 80:
            suggested += "..."
        lines.extend(
            [
                f"#### {i}. {regex_opp.description}",
                f"- **Performance Gain:** {regex_opp.performance_gain}",
                f"- **Suggested Regex:** `{suggested}`",
                f"- **File:** {regex_opp.locations[0].file_path if regex_opp.locations else 'N/A'}",
                "",
            ]
        )
    if len(report.regex_opportunities) > 5:
        lines.append(
            f"*... and {len(report.regex_opportunities) - 5} more opportunities*"
        )
        lines.append("")
    return lines


def _generate_complexity_hotspots_section(report: PatternAnalysisReport) -> List[str]:
    """Generate complexity hotspots section (Issue #560: extracted)."""
    if not report.complexity_hotspots:
        return []

    lines = [
        "### 🔥 Complexity Hotspots",
        "",
        f"> **{len(report.complexity_hotspots)} high-complexity areas identified**",
        "",
        "| Function | File | Cyclomatic | Cognitive | Nesting |",
        "|----------|------|------------|-----------|---------|",
    ]
    sorted_hotspots = sorted(
        report.complexity_hotspots, key=lambda h: h.cyclomatic_complexity, reverse=True
    )[
        :15
    ]  # Top 15

    for hotspot in sorted_hotspots:
        func_name = (
            hotspot.locations[0].function_name if hotspot.locations else "unknown"
        )
        file_path = hotspot.locations[0].file_path if hotspot.locations else "N/A"
        short_path = file_path.split("/")[-1] if "/" in file_path else file_path
        lines.append(
            f"| `{func_name[:30]}` | `{short_path[:25]}` | {hotspot.cyclomatic_complexity} | "
            f"{hotspot.cognitive_complexity} | {hotspot.nesting_depth} |"
        )
    lines.append("")
    return lines


def _generate_pattern_recommendations(report: PatternAnalysisReport) -> List[str]:
    """Generate recommendations section (Issue #560: extracted)."""
    high_severity_count = 0
    if report.duplicate_patterns:
        high_severity_count = len(
            [
                d
                for d in report.duplicate_patterns
                if hasattr(d.severity, "value") and d.severity.value == "high"
            ]
        )
    regex_count = len(report.regex_opportunities) if report.regex_opportunities else 0

    return [
        "### Recommendations",
        "",
        f"- **Priority:** Address {high_severity_count} high-severity duplicates first",
        f"- **Quick Wins:** Implement {regex_count} regex optimizations for better performance",
        "- **Refactoring:** Simplify top complexity hotspots to improve maintainability",
        "",
        "---",
        "",
    ]


def _generate_pattern_analysis_section(
    report: Optional[PatternAnalysisReport],
) -> List[str]:
    """
    Generate the Code Pattern Analysis section for the report (Issue #208).

    Issue #560: Refactored to use helper functions for better maintainability.

    Args:
        report: PatternAnalysisReport from CodePatternAnalyzer

    Returns:
        List of markdown lines for the pattern analysis section
    """
    if not report or report.total_patterns == 0:
        return []

    lines = [
        "## 🔍 Code Pattern Analysis",
        "",
        "> **Analysis of code patterns, duplicates, complexity hotspots, and optimization opportunities.**",
        "",
    ]

    lines.extend(_generate_pattern_overview(report))
    lines.extend(_generate_severity_distribution(report))
    lines.extend(_generate_duplicate_patterns_section(report))
    lines.extend(_generate_regex_opportunities_section(report))
    lines.extend(_generate_complexity_hotspots_section(report))
    lines.extend(_generate_pattern_recommendations(report))

    return lines


def _generate_cross_language_section(
    analysis: Optional[CrossLanguageAnalysis],
) -> List[str]:
    """
    Generate the Cross-Language Pattern Analysis section for the report (Issue #244).

    Args:
        analysis: CrossLanguageAnalysis from CrossLanguagePatternDetector

    Returns:
        List of markdown lines for the cross-language section
    """
    if not analysis:
        return []

    # Skip if no findings
    has_findings = (
        analysis.dto_mismatches
        or analysis.api_contract_mismatches
        or analysis.validation_duplications
        or analysis.pattern_matches
    )

    if not has_findings:
        return []

    lines = [
        "## 🌐 Cross-Language Pattern Analysis",
        "",
        "> **Analysis of patterns across Python (backend) and TypeScript/Vue (frontend).**",
        "",
    ]

    lines.extend(_generate_cross_language_overview(analysis))
    lines.extend(_generate_dto_mismatches_section(analysis))
    lines.extend(_generate_api_mismatches_section(analysis))
    lines.extend(_generate_validation_duplications_section(analysis))
    lines.extend(_generate_semantic_matches_section(analysis))

    # Summary statistics
    critical_count = analysis.critical_issues
    high_count = analysis.high_issues

    if critical_count > 0 or high_count > 0:
        lines.extend(
            [
                "### Issue Summary",
                "",
                f"- 🔴 **Critical Issues:** {critical_count}",
                f"- 🟠 **High Issues:** {high_count}",
                f"- 🟡 **Medium Issues:** {analysis.medium_issues}",
                f"- 🟢 **Low Issues:** {analysis.low_issues}",
                "",
            ]
        )

    lines.extend(["---", ""])

    return lines


def _fetch_problems_from_chromadb() -> List[Dict]:
    """
    Fetch code problems from ChromaDB collection.

    Returns:
        List of problem dictionaries with type, severity, file_path, etc.
    """
    code_collection = get_code_collection()
    problems = []

    if not code_collection:
        return problems

    try:
        results = code_collection.get(
            where={"type": "problem"},
            include=["metadatas"],
        )

        if results and results.get("metadatas"):
            for metadata in results["metadatas"]:
                problems.append(
                    {
                        "type": metadata.get("problem_type", "unknown"),
                        "severity": metadata.get("severity", "low"),
                        "file_path": metadata.get("file_path", ""),
                        "file_category": metadata.get(
                            "file_category", FILE_CATEGORY_CODE
                        ),
                        "line_number": metadata.get("line_number"),
                        "description": metadata.get("description", ""),
                        "suggestion": metadata.get("suggestion", ""),
                    }
                )

        logger.info("Retrieved %s problems for report", len(problems))
    except Exception as e:
        logger.error("Failed to fetch problems from ChromaDB: %s", e)

    return problems


def _build_analysis_task_list(
    include_bug_prediction: bool,
    include_api_analysis: bool,
    include_duplicate_analysis: bool,
    include_cross_language_analysis: bool,
    include_pattern_analysis: bool,
    use_semantic: bool,
) -> List[Tuple[str, Any]]:
    """
    Build list of analysis tasks to run based on flags.

    Issue #620: Extracted from _run_parallel_analyses.
    """
    tasks = []
    if include_bug_prediction:
        tasks.append(("bug_prediction", _get_bug_prediction(use_semantic=use_semantic)))
    if include_api_analysis:
        tasks.append(("api_endpoint", _get_api_endpoint_analysis()))
    if include_duplicate_analysis:
        tasks.append(("duplicate", _get_duplicate_analysis()))
    if include_cross_language_analysis:
        tasks.append(("cross_language", _get_cross_language_analysis()))
    if include_pattern_analysis:
        tasks.append(("pattern_analysis", _get_pattern_analysis()))
    return tasks


def _get_empty_analysis_result() -> Dict[str, Optional[object]]:
    """
    Return empty analysis result dictionary.

    Issue #620: Extracted from _run_parallel_analyses.
    """
    return {
        "bug_prediction": None,
        "api_endpoint": None,
        "duplicate": None,
        "cross_language": None,
        "pattern_analysis": None,
    }


async def _run_parallel_analyses(
    include_bug_prediction: bool,
    include_api_analysis: bool,
    include_duplicate_analysis: bool,
    include_cross_language_analysis: bool,
    include_pattern_analysis: bool,
    use_semantic: bool,
) -> Dict[str, Optional[object]]:
    """
    Run multiple code analyses in parallel.

    Issue #620: Refactored to use extracted helpers.
    """
    analysis_tasks = _build_analysis_task_list(
        include_bug_prediction,
        include_api_analysis,
        include_duplicate_analysis,
        include_cross_language_analysis,
        include_pattern_analysis,
        use_semantic,
    )
    result = _get_empty_analysis_result()

    if not analysis_tasks:
        return result

    # Run all analyses in parallel with individual error handling
    results = await asyncio.gather(
        *[task for _, task in analysis_tasks], return_exceptions=True
    )

    # Map results back to dict
    for i, (task_name, _) in enumerate(analysis_tasks):
        task_result = results[i]
        if isinstance(task_result, Exception):
            logger.warning("Analysis %s failed: %s", task_name, task_result)
            continue
        result[task_name] = task_result

    return result


def _build_empty_report_header() -> List[str]:
    """
    Build header for empty report (no code issues detected).

    Issue #620: Extracted from _generate_empty_report_with_analyses.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return [
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


def _check_has_analyses(
    api_endpoint_analysis: Optional[APIEndpointAnalysis],
    duplicate_analysis: Optional[DuplicateAnalysis],
    cross_language_analysis: Optional[CrossLanguageAnalysis],
    pattern_analysis: Optional[PatternAnalysisReport],
    bug_prediction: Optional[PredictionResult],
) -> bool:
    """
    Check if any analyses have meaningful results.

    Issue #620: Extracted from _generate_empty_report_with_analyses.
    """
    return bool(
        api_endpoint_analysis
        or (duplicate_analysis and duplicate_analysis.total_duplicates > 0)
        or (cross_language_analysis and cross_language_analysis.total_patterns > 0)
        or (pattern_analysis and pattern_analysis.total_patterns > 0)
        or (bug_prediction and bug_prediction.analyzed_files > 0)
    )


def _generate_empty_report_with_analyses(
    api_endpoint_analysis: Optional[APIEndpointAnalysis],
    duplicate_analysis: Optional[DuplicateAnalysis],
    cross_language_analysis: Optional[CrossLanguageAnalysis],
    pattern_analysis: Optional[PatternAnalysisReport],
    bug_prediction: Optional[PredictionResult],
) -> str:
    """
    Generate report when no code issues are detected but analyses are available.

    Issue #620: Refactored to use extracted helpers.
    """
    lines = _build_empty_report_header()

    # Add analysis sections (Issue #620: use extracted helper with condition checks)
    if api_endpoint_analysis:
        lines.extend(_generate_api_endpoint_section(api_endpoint_analysis))
    if duplicate_analysis and duplicate_analysis.total_duplicates > 0:
        lines.extend(_generate_duplicate_code_section(duplicate_analysis))
    if cross_language_analysis and cross_language_analysis.total_patterns > 0:
        lines.extend(_generate_cross_language_section(cross_language_analysis))
    if pattern_analysis and pattern_analysis.total_patterns > 0:
        lines.extend(_generate_pattern_analysis_section(pattern_analysis))
    if bug_prediction and bug_prediction.analyzed_files > 0:
        lines.extend(_generate_bug_risk_section(bug_prediction))

    if not _check_has_analyses(
        api_endpoint_analysis,
        duplicate_analysis,
        cross_language_analysis,
        pattern_analysis,
        bug_prediction,
    ):
        lines.append('Run "Index Codebase" first to analyze the code.')
        lines.append("")

    lines.append("*Report generated by AutoBot Code Analysis*")
    return "\n".join(lines)


async def _get_cross_language_analysis() -> Optional[CrossLanguageAnalysis]:
    """
    Get cross-language pattern analysis for the project (Issue #244).

    Returns:
        CrossLanguageAnalysis or None if analysis fails
    """
    try:
        detector = CrossLanguagePatternDetector(
            use_llm=True,
            use_cache=True,
        )

        analysis = await asyncio.wait_for(
            detector.run_analysis(),
            timeout=120.0,  # 2 minute timeout
        )

        logger.info(
            "Cross-language analysis: %d patterns, %d DTO mismatches, %d API mismatches",
            analysis.total_patterns,
            len(analysis.dto_mismatches),
            len(analysis.api_contract_mismatches),
        )
        return analysis
    except asyncio.TimeoutError:
        logger.warning("Cross-language analysis timed out")
        return None
    except Exception as e:
        logger.error("Cross-language analysis failed: %s", e, exc_info=True)
        return None


async def _get_pattern_analysis() -> Optional[PatternAnalysisReport]:
    """
    Get code pattern analysis for the project (Issue #208).

    Returns:
        PatternAnalysisReport or None if analysis fails
    """
    try:
        project_root = str(Path(__file__).resolve().parents[4])

        analyzer = CodePatternAnalyzer(
            enable_clone_detection=True,
            enable_anti_pattern_detection=True,
            enable_regex_detection=True,
            enable_complexity_analysis=True,
            similarity_threshold=0.8,
        )

        report = await asyncio.wait_for(
            analyzer.analyze_directory(project_root),
            timeout=180.0,  # 3 minute timeout for comprehensive analysis
        )

        logger.info(
            "Pattern analysis: %d patterns, %d duplicates, %d complexity hotspots",
            report.total_patterns,
            len(report.duplicate_patterns),
            len(report.complexity_hotspots),
        )
        return report
    except asyncio.TimeoutError:
        logger.warning("Pattern analysis timed out")
        return None
    except Exception as e:
        logger.error("Pattern analysis failed: %s", e, exc_info=True)
        return None


async def _get_duplicate_analysis() -> Optional[DuplicateAnalysis]:
    """
    Get duplicate code analysis for the project (Issue #528).

    Returns:
        DuplicateAnalysis or None if analysis fails
    """
    try:
        loop = asyncio.get_event_loop()
        project_root = str(Path(__file__).resolve().parents[4])

        analysis = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: DuplicateCodeDetector(project_root=project_root).run_analysis(),
            ),
            timeout=60.0,  # 60 second timeout for duplicate detection
        )

        logger.info(
            "Duplicate analysis: %d duplicates (%d high, %d medium, %d low)",
            analysis.total_duplicates,
            analysis.high_similarity_count,
            analysis.medium_similarity_count,
            analysis.low_similarity_count,
        )
        return analysis
    except asyncio.TimeoutError:
        logger.warning("Duplicate analysis timed out")
        return None
    except Exception as e:
        logger.error("Duplicate analysis failed: %s", e, exc_info=True)
        return None


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
    use_semantic: bool = False,
) -> Optional[PredictionResult]:
    """
    Get bug prediction data for the project (Issue #505).

    Runs the analysis in a thread pool to avoid blocking the async event loop.

    Issue #554: Enhanced with optional semantic analysis:
    - use_semantic=True enables LLM-based bug pattern matching
    - Uses ChromaDB for vector similarity and Redis for caching

    Args:
        project_root: Root directory to analyze (defaults to current directory)
        limit: Maximum number of files to analyze
        use_semantic: Enable semantic analysis via LLM embeddings (Issue #554)

    Returns:
        PredictionResult or None if analysis fails or times out
    """
    try:
        # Use project root or default to current working directory
        root = project_root or str(Path.cwd())

        # Run in thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()

        # Issue #554: Pass semantic analysis flag
        predictor = BugPredictor(project_root=root, use_semantic_analysis=use_semantic)

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
        logger.warning("Bug prediction timed out after %ss", BUG_PREDICTION_TIMEOUT)
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
        by_category[FILE_CATEGORY_CODE]
        + by_category[FILE_CATEGORY_CONFIG]
        + by_category[FILE_CATEGORY_TEST]
    )
    if code_problems:
        lines.extend(
            _generate_category_section(
                code_problems,
                FILE_CATEGORY_CODE,
                "📄 Code, Configuration & Test Issues",
                note="**Priority:** These issues should be fixed.",
            )
        )
        lines.extend(["---", ""])

    # Section 2: Backup File Issues (informational)
    if by_category[FILE_CATEGORY_BACKUP]:
        lines.extend(
            _generate_category_section(
                by_category[FILE_CATEGORY_BACKUP],
                FILE_CATEGORY_BACKUP,
                "📦 Backup File Issues",
                note="**Note:** These are backup files kept for rollback. "
                "Fix only if restoring these files.",
            )
        )
        lines.extend(["---", ""])

    # Section 3: Archive File Issues (informational)
    if by_category[FILE_CATEGORY_ARCHIVE]:
        lines.extend(
            _generate_category_section(
                by_category[FILE_CATEGORY_ARCHIVE],
                FILE_CATEGORY_ARCHIVE,
                "🗄️ Archived File Issues",
                note="**Note:** These are archived/deprecated files. "
                "Usually do not require fixes.",
            )
        )
        lines.extend(["---", ""])

    # Section 4: Docs & Logs Issues (informational)
    docs_logs = by_category[FILE_CATEGORY_DOCS] + by_category[FILE_CATEGORY_LOGS]
    if docs_logs:
        lines.extend(
            _generate_category_section(
                docs_logs,
                FILE_CATEGORY_DOCS,
                "📝 Documentation & Log File Issues",
                note="**Note:** Issues in documentation or log files.",
            )
        )
        lines.extend(["---", ""])

    return lines


def _compute_correlation_data(
    problems: List[Dict],
    prediction: PredictionResult,
) -> Tuple[Set[str], Dict[str, Any], Set[str]]:
    """
    Compute file sets and overlap for correlation analysis.

    Issue #620: Extracted from _build_correlation_section.

    Returns:
        Tuple of (files_with_issues, high_risk_files_dict, overlap_set)
    """
    files_with_issues = set(
        p.get("file_path", "") for p in problems if p.get("file_path")
    )
    high_risk_files = {
        fa.file_path: fa
        for fa in prediction.file_assessments
        if fa.risk_level.value in ("critical", "high")
    }
    overlap = files_with_issues & set(high_risk_files.keys())
    return files_with_issues, high_risk_files, overlap


def _format_correlation_table(
    problems: List[Dict],
    overlap: Set[str],
    high_risk_files: Dict[str, Any],
) -> List[str]:
    """
    Format the correlation table for overlapping files.

    Issue #620: Extracted from _build_correlation_section.
    """
    lines = [
        "**Priority Files (Issues + High Bug Risk):**",
        "",
        "| File | Issue Count | Risk Score | Risk Level |",
        "|------|-------------|------------|------------|",
    ]

    # Count issues per file
    issue_counts: Dict[str, int] = {}
    for p in problems:
        fp = p.get("file_path", "")
        if fp in overlap:
            issue_counts[fp] = issue_counts.get(fp, 0) + 1

    # Sort by risk score
    sorted_overlap = sorted(
        overlap, key=lambda f: high_risk_files[f].risk_score, reverse=True
    )

    for file_path in sorted_overlap[:10]:
        fa = high_risk_files[file_path]
        issue_count = issue_counts.get(file_path, 0)
        emoji = _get_risk_emoji(fa.risk_level.value)
        lines.append(
            f"| `{file_path}` | {issue_count} | {fa.risk_score:.1f} | "
            f"{emoji} {fa.risk_level.value.capitalize()} |"
        )

    lines.extend(
        [
            "",
            f"> **{len(overlap)} files** have both detected issues and high bug risk. "
            "These should be prioritized for review.",
            "",
        ]
    )
    return lines


def _build_correlation_section(
    problems: List[Dict],
    prediction: Optional[PredictionResult],
) -> List[str]:
    """
    Build cross-reference section showing files with both issues AND high risk.

    Issue #505: Original implementation.
    Issue #620: Refactored to use extracted helper methods.

    Args:
        problems: List of detected code issues
        prediction: Bug prediction result

    Returns:
        List of markdown lines for correlation section
    """
    if not prediction:
        return []

    _, high_risk_files, overlap = _compute_correlation_data(problems, prediction)

    if overlap:
        return _format_correlation_table(problems, overlap, high_risk_files)

    return [
        "*No files appear in both static analysis issues and high bug risk.*",
        "",
    ]


def _insert_correlation_into_bug_risk(
    bug_risk_lines: List[str],
    correlation_lines: List[str],
) -> List[str]:
    """
    Insert correlation data into the bug risk section.

    Issue #665: Extracted from _generate_markdown_report to reduce function length.

    Args:
        bug_risk_lines: Lines from _generate_bug_risk_section
        correlation_lines: Lines from _build_correlation_section

    Returns:
        Modified bug_risk_lines with correlation data inserted
    """
    if not correlation_lines:
        return bug_risk_lines

    # Find where to insert correlation (at the "Correlation with Detected Issues" header)
    insert_idx = None
    for i, line in enumerate(bug_risk_lines):
        if line == "### Correlation with Detected Issues":
            insert_idx = i
            break

    if insert_idx is not None:
        # Remove placeholder and insert real data
        # Keep header + blank + note, then insert correlation, then final --- and blank
        return (
            bug_risk_lines[: insert_idx + 3] + correlation_lines + bug_risk_lines[-2:]
        )

    return bug_risk_lines


def _build_analysis_sections(
    api_endpoint_analysis: Optional[APIEndpointAnalysis],
    duplicate_analysis: Optional[DuplicateAnalysis],
    cross_language_analysis: Optional[CrossLanguageAnalysis],
    pattern_analysis: Optional[PatternAnalysisReport],
) -> List[str]:
    """
    Build all analysis sections for the report.

    Issue #665: Extracted from _generate_markdown_report to reduce function length.

    Args:
        api_endpoint_analysis: API endpoint analysis result
        duplicate_analysis: Duplicate code analysis result
        cross_language_analysis: Cross-language pattern analysis result
        pattern_analysis: Code pattern analysis result

    Returns:
        List of markdown lines for all analysis sections
    """
    lines = []

    # Add API endpoint analysis section (Issue #527)
    if api_endpoint_analysis:
        lines.extend(_generate_api_endpoint_section(api_endpoint_analysis))

    # Add duplicate code analysis section (Issue #528)
    if duplicate_analysis:
        lines.extend(_generate_duplicate_code_section(duplicate_analysis))

    # Add cross-language pattern analysis section (Issue #244)
    if cross_language_analysis:
        lines.extend(_generate_cross_language_section(cross_language_analysis))

    # Add code pattern analysis section (Issue #208)
    if pattern_analysis:
        lines.extend(_generate_pattern_analysis_section(pattern_analysis))

    return lines


def _build_bug_prediction_section(
    bug_prediction: Optional[PredictionResult],
    problems: List[Dict],
) -> List[str]:
    """
    Build bug prediction section with correlation data.

    Issue #665: Extracted from _generate_markdown_report to reduce function length.

    Args:
        bug_prediction: Bug prediction analysis result
        problems: List of detected code issues

    Returns:
        List of markdown lines for bug prediction section
    """
    if not bug_prediction:
        return []

    bug_risk_lines = _generate_bug_risk_section(bug_prediction)
    correlation_lines = _build_correlation_section(problems, bug_prediction)

    return _insert_correlation_into_bug_risk(bug_risk_lines, correlation_lines)


def _generate_markdown_report(
    problems: List[Dict],
    analyzed_path: Optional[str] = None,
    bug_prediction: Optional[PredictionResult] = None,
    api_endpoint_analysis: Optional[APIEndpointAnalysis] = None,
    duplicate_analysis: Optional[DuplicateAnalysis] = None,
    cross_language_analysis: Optional[CrossLanguageAnalysis] = None,
    pattern_analysis: Optional[PatternAnalysisReport] = None,
) -> str:
    """
    Generate a Markdown report from problems list.

    Issue #398: Initial refactoring. Issue #505: Bug prediction.
    Issue #620: Refactored to use _build_analysis_sections helper.

    Problems are separated by file category (code, backup, archive, docs/logs).
    Includes: API endpoint, duplicate code, cross-language, pattern, and bug prediction analyses.
    """
    path_info = analyzed_path or "Unknown"
    by_category = _separate_by_category(problems)

    # Calculate statistics
    counts = _calculate_category_counts(by_category)
    severity_counts, type_counts = _calculate_severity_and_type_counts(problems)

    # Build report sections using extracted helpers (Issue #620)
    lines = _build_report_header(path_info, len(problems), counts)
    lines.extend(_build_summary_section(severity_counts, type_counts))
    lines.extend(
        _build_analysis_sections(
            api_endpoint_analysis,
            duplicate_analysis,
            cross_language_analysis,
            pattern_analysis,
        )
    )
    lines.extend(_build_bug_prediction_section(bug_prediction, problems))
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
    include_duplicate_analysis: bool = True,
    include_bug_prediction: bool = True,
    include_cross_language_analysis: bool = True,
    include_pattern_analysis: bool = True,
    quick: bool = False,
    use_semantic: bool = False,
):
    """
    Generate a code analysis report from the indexed data.

    Args:
        format: Output format (currently only 'markdown' supported)
        include_api_analysis: Whether to include API endpoint analysis (Issue #527)
        include_duplicate_analysis: Whether to include duplicate code analysis (Issue #528)
        include_bug_prediction: Whether to include bug prediction analysis (Issue #505)
        include_cross_language_analysis: Whether to include cross-language pattern analysis (Issue #244)
        include_pattern_analysis: Whether to include code pattern analysis (Issue #208)
        quick: If True, skip expensive analyses for faster export (just problems report)
        use_semantic: Enable LLM-based semantic analysis for bug prediction (Issue #554)

    Returns:
        Markdown formatted report as plain text
    """
    # Fetch problems from indexed data
    problems = _fetch_problems_from_chromadb()

    # Get analysis results (or skip in quick mode)
    if quick:
        logger.info("Quick mode: Skipping expensive analyses")
        analyses = {
            "bug_prediction": None,
            "api_endpoint": None,
            "duplicate": None,
            "cross_language": None,
            "pattern_analysis": None,
        }
    else:
        analyses = await _run_parallel_analyses(
            include_bug_prediction=include_bug_prediction,
            include_api_analysis=include_api_analysis,
            include_duplicate_analysis=include_duplicate_analysis,
            include_cross_language_analysis=include_cross_language_analysis,
            include_pattern_analysis=include_pattern_analysis,
            use_semantic=use_semantic,
        )

    # Generate the report
    if not problems:
        report = _generate_empty_report_with_analyses(
            api_endpoint_analysis=analyses["api_endpoint"],
            duplicate_analysis=analyses["duplicate"],
            cross_language_analysis=analyses["cross_language"],
            pattern_analysis=analyses["pattern_analysis"],
            bug_prediction=analyses["bug_prediction"],
        )
    else:
        report = _generate_markdown_report(
            problems,
            analyzed_path="Indexed Codebase",
            bug_prediction=analyses["bug_prediction"],
            api_endpoint_analysis=analyses["api_endpoint"],
            duplicate_analysis=analyses["duplicate"],
            cross_language_analysis=analyses["cross_language"],
            pattern_analysis=analyses["pattern_analysis"],
        )

    return PlainTextResponse(
        content=report,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="code-analysis-report.md"',
        },
    )
