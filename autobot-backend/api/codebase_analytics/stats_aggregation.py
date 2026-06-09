# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Statistics and result aggregation functions for codebase analytics.

Issue #2013: Decomposed from scanner.py god module.
"""

from datetime import datetime, timezone
from typing import Dict, List

from autobot_shared.logging_manager import get_logger
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

from .types import FileAnalysisResult

logger = get_logger(__name__)


def _aggregate_stats_for_countable(stats: Dict, file_analysis: Dict, file_line_count: int) -> None:
    """
    Aggregate stats for countable file categories (code/config/test).

    Issue #398: Extracted from _aggregate_file_analysis to reduce method length.
    """
    stats["total_lines"] += file_line_count
    stats["total_functions"] += len(file_analysis.get("functions", []))
    stats["total_classes"] += len(file_analysis.get("classes", []))
    stats["code_lines"] += file_analysis.get("code_lines", 0)
    stats["comment_lines"] += file_analysis.get("comment_lines", 0)
    stats["docstring_lines"] += file_analysis.get("docstring_lines", 0)
    stats["blank_lines"] += file_analysis.get("blank_lines", 0)


def _aggregate_items_to_list(items: List[Dict], target_list: list, relative_path: str, file_category: str) -> None:
    """
    Add file_path and file_category to items and append to target list.

    Issue #398: Extracted from _aggregate_file_analysis to reduce method length.
    """
    for item in items:
        item["file_path"] = relative_path
        item["file_category"] = file_category
        target_list.append(item)


def _aggregate_file_analysis(
    analysis_results: Dict,
    file_analysis: Dict,
    relative_path: str,
    file_category: str = FILE_CATEGORY_CODE,
) -> None:
    """
    Aggregate file analysis results into main results dict.

    Issue #398: Refactored with extracted helpers.
    """
    analysis_results["files"][relative_path] = file_analysis
    file_line_count = file_analysis.get("line_count", 0)
    stats = analysis_results["stats"]

    stats["lines_by_category"][file_category] += file_line_count
    stats["files_by_category"][file_category] += 1

    is_countable = file_category in (
        FILE_CATEGORY_CODE,
        FILE_CATEGORY_CONFIG,
        FILE_CATEGORY_TEST,
    )
    if is_countable:
        _aggregate_stats_for_countable(stats, file_analysis, file_line_count)

    stats["documentation_lines"] += file_analysis.get("documentation_lines", 0)

    all_funcs = analysis_results["all_functions"]
    all_cls = analysis_results["all_classes"]
    all_hc = analysis_results["all_hardcodes"]
    _aggregate_items_to_list(file_analysis.get("functions", []), all_funcs, relative_path, file_category)
    _aggregate_items_to_list(file_analysis.get("classes", []), all_cls, relative_path, file_category)
    _aggregate_items_to_list(file_analysis.get("hardcodes", []), all_hc, relative_path, file_category)


def _create_empty_category_dict(default_value=0) -> Dict:
    """
    Create a dictionary with all file categories initialized to a default value.

    Issue #620: Extracted from _create_empty_analysis_results. Issue #620.
    """
    return {
        FILE_CATEGORY_CODE: default_value if default_value != 0 else 0,
        FILE_CATEGORY_DOCS: default_value if default_value != 0 else 0,
        FILE_CATEGORY_LOGS: default_value if default_value != 0 else 0,
        FILE_CATEGORY_BACKUP: default_value if default_value != 0 else 0,
        FILE_CATEGORY_ARCHIVE: default_value if default_value != 0 else 0,
        FILE_CATEGORY_CONFIG: default_value if default_value != 0 else 0,
        FILE_CATEGORY_TEST: default_value if default_value != 0 else 0,
        FILE_CATEGORY_DATA: default_value if default_value != 0 else 0,
        FILE_CATEGORY_ASSETS: default_value if default_value != 0 else 0,
    }


def _create_empty_category_list_dict() -> Dict:
    """
    Create a dictionary with all file categories initialized to empty lists.

    Issue #620: Extracted from _create_empty_analysis_results. Issue #620.
    """
    return {
        FILE_CATEGORY_CODE: [],
        FILE_CATEGORY_DOCS: [],
        FILE_CATEGORY_LOGS: [],
        FILE_CATEGORY_BACKUP: [],
        FILE_CATEGORY_ARCHIVE: [],
        FILE_CATEGORY_CONFIG: [],
        FILE_CATEGORY_TEST: [],
        FILE_CATEGORY_DATA: [],
        FILE_CATEGORY_ASSETS: [],
    }


def _create_empty_stats_dict() -> Dict:
    """
    Create the stats dictionary structure for analysis results.

    Issue #620: Extracted from _create_empty_analysis_results. Issue #620.
    """
    return {
        "total_files": 0,
        "python_files": 0,
        "javascript_files": 0,
        "typescript_files": 0,
        "vue_files": 0,
        "css_files": 0,
        "html_files": 0,
        "config_files": 0,
        "doc_files": 0,
        "other_code_files": 0,
        "other_files": 0,
        "total_lines": 0,
        "code_lines": 0,
        "comment_lines": 0,
        "docstring_lines": 0,
        "documentation_lines": 0,
        "blank_lines": 0,
        "total_functions": 0,
        "total_classes": 0,
        "lines_by_category": _create_empty_category_dict(0),
        "files_by_category": _create_empty_category_dict(0),
    }


def _create_empty_analysis_results() -> Dict:
    """
    Create empty analysis results dictionary structure.

    Issue #281: Extracted from scan_codebase to reduce function length.
    Issue #620: Further refactored with helper functions. Issue #620.

    Returns:
        Dict with initialized structure for files, stats, functions,
        classes, hardcodes, and problems.
    """
    return {
        "files": {},
        "stats": _create_empty_stats_dict(),
        "all_functions": [],
        "all_classes": [],
        "all_hardcodes": [],
        "all_problems": [],
        "problems_by_category": _create_empty_category_list_dict(),
    }


def _calculate_analysis_statistics(analysis_results: Dict) -> None:
    """
    Calculate derived statistics for analysis results.

    Issue #281: Extracted from scan_codebase to reduce function length.
    Modifies analysis_results in place.

    Calculates:
        - average_file_size: Average lines per file
        - comment_ratio: Percentage of comment lines
        - docstring_ratio: Percentage of docstring lines
        - documentation_ratio: Combined comment + docstring percentage
        - last_indexed: Timestamp of indexing
    """
    stats = analysis_results["stats"]

    # Calculate average file size
    if stats["total_files"] > 0:
        stats["average_file_size"] = stats["total_lines"] / stats["total_files"]
    else:
        stats["average_file_size"] = 0

    # Calculate documentation ratios (Issue #368)
    total_lines = stats["total_lines"]
    if total_lines > 0:
        comment_lines = stats["comment_lines"]
        docstring_lines = stats["docstring_lines"]
        stats["comment_ratio"] = f"{(comment_lines / total_lines * 100):.1f}%"
        stats["docstring_ratio"] = f"{(docstring_lines / total_lines * 100):.1f}%"
        # Combined documentation ratio (comments + docstrings)
        doc_total = comment_lines + docstring_lines
        stats["documentation_ratio"] = f"{(doc_total / total_lines * 100):.1f}%"
    else:
        stats["comment_ratio"] = "0.0%"
        stats["docstring_ratio"] = "0.0%"
        stats["documentation_ratio"] = "0.0%"

    stats["last_indexed"] = datetime.now(tz=timezone.utc).isoformat()


def _update_file_type_stats(stats: Dict, result: "FileAnalysisResult") -> None:
    """
    Update file type statistics from a FileAnalysisResult.

    Issue #620: Extracted from _aggregate_from_file_result. Issue #620.
    """
    if result.stat_key:
        stats[result.stat_key] = stats.get(result.stat_key, 0) + 1
    else:
        stats["other_files"] = stats.get("other_files", 0) + 1
    stats["total_files"] += 1


def _update_countable_category_stats(stats: Dict, result: "FileAnalysisResult") -> None:
    """
    Update stats for countable file categories (code, config, test).

    Issue #620: Extracted from _aggregate_from_file_result. Issue #620.
    """
    stats["total_lines"] += result.line_count
    stats["total_functions"] += len(result.functions)
    stats["total_classes"] += len(result.classes)
    stats["code_lines"] += result.code_lines
    stats["comment_lines"] += result.comment_lines
    stats["docstring_lines"] += result.docstring_lines
    stats["blank_lines"] += result.blank_lines


def _aggregate_from_file_result(
    analysis_results: Dict,
    result: "FileAnalysisResult",
) -> None:
    """
    Aggregate a single FileAnalysisResult into the main results dict.

    Issue #711: Helper for single-pass aggregation from immutable results.
    Issue #620: Refactored with helper functions. Issue #620.

    Args:
        analysis_results: Main results dictionary to update
        result: Single FileAnalysisResult to aggregate
    """
    if not result.was_processed:
        return

    file_category = result.file_category
    stats = analysis_results["stats"]

    analysis_results["files"][result.relative_path] = result.to_dict()
    _update_file_type_stats(stats, result)

    stats["lines_by_category"][file_category] += result.line_count
    stats["files_by_category"][file_category] += 1

    is_countable = file_category in (
        FILE_CATEGORY_CODE,
        FILE_CATEGORY_CONFIG,
        FILE_CATEGORY_TEST,
    )
    if is_countable:
        _update_countable_category_stats(stats, result)

    stats["documentation_lines"] += result.documentation_lines

    analysis_results["all_functions"].extend(result.functions)
    analysis_results["all_classes"].extend(result.classes)
    analysis_results["all_hardcodes"].extend(result.hardcodes)
    analysis_results["all_problems"].extend(result.problems)
    analysis_results["problems_by_category"][file_category].extend(result.problems)


def _aggregate_all_results(
    all_results: List[FileAnalysisResult],
) -> Dict:
    """
    Aggregate all FileAnalysisResult objects into a single results dictionary.

    Issue #711: Thread-safe single-pass aggregation after parallel processing.
    This runs AFTER all parallel processing is complete, operating on
    immutable input data, so there are no thread-safety concerns.

    Args:
        all_results: List of FileAnalysisResult from parallel processing

    Returns:
        Complete analysis_results dictionary matching existing format
    """
    analysis_results = _create_empty_analysis_results()

    for result in all_results:
        _aggregate_from_file_result(analysis_results, result)

    _calculate_analysis_statistics(analysis_results)
    return analysis_results
