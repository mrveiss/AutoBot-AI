# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for quick_microservice_analysis's markdown report (#15585).

``_generate_markdown_report``, ``_generate_migration_phases_md`` and the block
under ``## Next Steps`` built their output from triple-double-quoted strings
containing ``{}`` placeholders with no ``f`` prefix, so every placeholder
rendered as literal text instead of the analysis value it names. One of those
blocks references ``metrics`` -- a name that was never bound in
``_generate_markdown_report`` (line 532 discarded ``analysis["codebase_metrics"]``
into nothing instead of assigning it). Asserting the ``f`` prefix is present
would not catch either defect on its own. This asserts the rendered report
contains real values pulled from the fixture data and contains no leftover
``{identifier`` placeholder shape anywhere in the output.
"""

import inspect
import re
import sys
from pathlib import Path

# Lives here, not beside the script it tests -- see microservice_architecture_evaluator_test.py
# in this same directory for the ci.yml path-list reasoning (#14563, #14518).
_SCRIPTS_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

import quick_microservice_analysis as qma  # noqa: E402

_LEFTOVER_PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_]")


def _fake_analysis() -> dict:
    return {
        "timestamp": "2026-01-01T00:00:00",
        "codebase_metrics": {
            "estimated_total_loc": 55000,
            "total_python_files": 400,
            "python_files_analyzed": 400,
            "microservice_readiness_score": 7,
        },
        "api_analysis": {
            "api_modules": 12,
            "total_endpoints": 88,
            "modules": [{"name": "chat_router", "endpoints": 14}],
        },
        "agent_analysis": {
            "agent_modules": 6,
            "agents": [{"type": "chat", "name": "ChatAgent"}],
        },
        "service_recommendations": [
            {
                "type": "api_service",
                "name": "ChatService",
                "priority": "high",
                "complexity": "medium",
                "rationale": "Handles a distinct, high-traffic domain.",
            }
        ],
        "migration_assessment": {
            "readiness_level": "high",
            "total_services": 3,
            "estimated_total_duration_weeks": 12,
            "recommendation": "Proceed with phased extraction.",
            "migration_phases": [
                {
                    "phase": 1,
                    "name": "Foundation Services",
                    "duration_weeks": 4,
                    "services": ["ChatService"],
                    "rationale": "Lowest-risk starting point.",
                }
            ],
        },
    }


def test_markdown_report_renders_real_values_not_placeholders():
    """Every {expr} in the report must have been substituted (#15585)."""
    report = qma._generate_markdown_report(_fake_analysis())

    assert not _LEFTOVER_PLACEHOLDER_RE.search(report), (
        "Report contains an un-substituted {identifier} placeholder -- "
        "a triple-quoted string is missing its f prefix"
    )

    assert "**Analysis Date:** 2026-01-01T00:00:00" in report
    assert "AutoBot shows **HIGH** readiness" in report
    assert "**Readiness Score:** 7/10" in report
    assert "**Recommended Services:** 3" in report
    assert "**Migration Duration:** 12 weeks" in report
    assert "**Recommendation:** Proceed with phased extraction." in report
    assert "**Estimated Total Lines of Code:** 55,000" in report
    assert "**Overall Size:** Large" in report
    assert "**API Modules:** 12" in report
    assert "**Total Endpoints:** 88" in report
    assert "**chat_router:** 14 endpoints" in report
    assert "**Agent Modules:** 6" in report
    assert "#### Phase 1: Foundation Services" in report
    assert "Lowest-risk starting point." in report
    assert "**Total Duration:** 12 weeks" in report
    assert "(~3 months)" in report
    assert "Based on the **HIGH** readiness assessment" in report


def test_metrics_is_now_bound_and_used():
    """`analysis["codebase_metrics"]` must be an assignment, not a discarded statement (#15585)."""
    source = inspect.getsource(qma._generate_markdown_report)
    assert 'metrics = analysis["codebase_metrics"]' in source
