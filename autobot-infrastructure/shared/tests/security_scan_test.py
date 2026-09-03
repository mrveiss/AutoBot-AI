# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Test for security_scan's markdown report header (#15585 sweep finding).

``generate_markdown_report`` built its header from a triple-double-quoted
string containing ``{}`` placeholders with no ``f`` prefix, so
``**Scan Date:**``, ``**Overall Status:**``, ``**Critical Issues:**`` and
``**Warnings:**`` rendered their placeholder syntax literally instead of the
scan's real values. This asserts the rendered report contains real values
from the fixture data and no leftover ``{identifier`` placeholder shape.
"""

import re
import sys
from pathlib import Path

import pytest

# Lives here, not beside the script it tests -- see microservice_architecture_evaluator_test.py
# in this same directory for the ci.yml path-list reasoning (#14563, #14518).
_SCRIPTS_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from security_scan import SecurityScanner  # noqa: E402

_LEFTOVER_PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_]")


@pytest.fixture
def scanner(tmp_path: Path) -> SecurityScanner:
    instance = SecurityScanner(project_root=tmp_path)
    instance.scan_results = {
        "timestamp": "2026-01-01T00:00:00",
        "summary": {"overall_status": "warning", "critical_issues": 0, "warnings": 3},
        "dependency_security": {},
        "static_analysis": {},
        "secret_detection": {"pattern_detection": {"secrets_found": 0}},
        "compliance_check": {},
    }
    return instance


def test_markdown_report_renders_real_values_not_placeholders(scanner: SecurityScanner):
    report = scanner.generate_markdown_report()

    assert not _LEFTOVER_PLACEHOLDER_RE.search(report), (
        "Report contains an un-substituted {identifier} placeholder -- "
        "a triple-quoted string is missing its f prefix"
    )
    assert "**Scan Date:** 2026-01-01T00:00:00" in report
    assert "**Overall Status:** WARNING" in report
    assert "**Critical Issues:** 0" in report
    assert "**Warnings:** 3" in report
