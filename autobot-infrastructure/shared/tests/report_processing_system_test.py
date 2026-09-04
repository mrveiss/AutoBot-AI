# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Test for report_processing_system's Processing Statistics block (#15585 sweep finding).

``_save_detailed_report`` built its "## Processing Statistics" table from a
triple-quoted string containing ``{}`` placeholders with no ``f`` prefix, so
every row rendered the placeholder syntax literally instead of the real
statistic -- the one block in this method that was not already an f-string,
which is itself evidence the omission was accidental. This asserts the
written report contains real values from the fixture data and no leftover
``{identifier`` placeholder shape.
"""

import asyncio
import re
import sys
from pathlib import Path

# Lives here, not beside the script it tests -- see enhance_workflow_ui_test.py in this same
# directory for the ci.yml path-list / `utilities` namespace-package reasoning (#14563, #14518).
_SCRIPTS_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from utilities.report_processing_system import ReportProcessingCoordinator  # noqa: E402

_LEFTOVER_PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_]")


def test_detailed_report_renders_real_values_not_placeholders(tmp_path: Path):
    coordinator = object.__new__(ReportProcessingCoordinator)
    summary = {
        "mission_info": {"timestamp": "2026-01-01T00:00:00"},
        "statistics": {
            "processing_time": 12.345,
            "total_files": 200,
            "processed_files": 195,
            "archived_files": 180,
            "errors_found": 3,
            "warnings_found": 7,
        },
        "discovery_summary": {},
        "analysis_summary": {
            "critical_files": 1,
            "warning_files": 4,
            "clean_files": 195,
            "top_error_patterns": ["Traceback (most recent call last)"],
        },
        "archive_summary": {"archive_location": "/data/archive", "categories_created": ["errors"]},
        "recommendations": ["Investigate the critical error before the next run."],
    }
    report_path = tmp_path / "detailed_report.md"

    asyncio.run(coordinator._save_detailed_report(summary, {}, {}, report_path))
    content = report_path.read_text(encoding="utf-8")

    assert not _LEFTOVER_PLACEHOLDER_RE.search(content), (
        "Report contains an un-substituted {identifier} placeholder -- "
        "a triple-quoted string is missing its f prefix"
    )
    assert "| Total Files | 200 |" in content
    assert "| Processed Files | 195 |" in content
    assert "| Archived Files | 180 |" in content
    assert "| Errors Found | 3 |" in content
    assert "| Warnings Found | 7 |" in content
    assert "| Processing Time | 12.35s |" in content
