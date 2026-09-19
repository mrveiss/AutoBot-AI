# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for microservice_architecture_evaluator's markdown report (#15585).

``_generate_markdown_report`` (and the two helpers it delegates to,
``_generate_component_analysis_md`` and ``_generate_service_boundaries_md``)
built their output from triple-double-quoted strings containing ``{}``
placeholders with no ``f`` prefix, so every placeholder rendered as literal
text instead of the analysis value it names. Asserting the ``f`` prefix is
present would not catch this class of bug -- a string whose placeholders
name attributes that do not exist would still pass. Instead this asserts the
rendered report contains real values pulled from the fixture data and
contains no leftover ``{identifier`` placeholder shape anywhere in the
output.
"""

import re
import sys
from pathlib import Path

import pytest

# Lives here, not beside the script it tests: ci.yml's shard command passes an
# explicit path list, and `.../shared/scripts` is not on it while
# `.../shared/tests` is. Same reasoning as enhance_workflow_ui_test.py in this
# same directory (#14563, #14518).
_SCRIPTS_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from microservice_architecture_evaluator import MicroserviceArchitectureEvaluator  # noqa: E402

# A leftover, un-substituted placeholder: `{` immediately followed by an
# identifier character, with no `f` prefix ever having evaluated it.
_LEFTOVER_PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_]")


def _fake_analysis_results() -> dict:
    """Build a minimal but complete analysis_results tree.

    Covers every section _generate_markdown_report, _generate_component_analysis_md
    and _generate_service_boundaries_md render, so the assertions can prove each
    placeholder resolved to the real fixture value below.
    """
    return {
        "timestamp": "2026-01-01T00:00:00",
        "project_structure": {
            "file_statistics": {
                "total_loc": 12345,
                "total_files": 200,
                "python_files": 150,
                "javascript_files": 40,
                "config_files": 10,
            },
            "architecture_patterns": {
                "microservice_readiness": 8,
                "mvc_pattern": True,
                "layered_architecture": False,
                "api_gateway_present": True,
            },
            "key_components": {
                "api_endpoints": {
                    "total_endpoints": 42,
                    "routers": [{"name": "chat_router", "endpoints": ["/chat", "/chat/history"]}],
                },
                "agents": {
                    "total_agents": 5,
                    "agent_types": {"chat": ["ChatAgent"], "vision": ["VisionAgent"]},
                },
                "data_models": {
                    "database_files": ["models/user.py"],
                    "database_types": ["postgresql", "redis"],
                    "model_classes": ["User", "Session"],
                },
                "utilities": {
                    "util_files": ["utils/a.py", "utils/b.py"],
                    "shared_utilities": ["structured_logger"],
                    "utility_types": {"validation": ["v1"]},
                },
            },
        },
        "dependency_analysis": {
            "coupling_analysis": {
                "high_coupling_modules": [
                    {"module": "core.orchestrator", "fan_out": 12, "fan_in": 8, "coupling_score": 20}
                ]
            },
            "shared_modules": [{"module": "autobot_shared.redis_client", "import_count": 37}],
            "circular_dependencies": [["module_a", "module_b", "module_a"]],
        },
        "service_boundaries": {
            "proposed_services": [
                {
                    "name": "ChatService",
                    "type": "api_service",
                    "estimated_complexity": 6,
                    "responsibilities": ["Handle chat requests", "Manage sessions"],
                }
            ],
            "boundary_rationale": {"ChatService": "Because chat is a distinct bounded context."},
            "shared_services": [{"name": "LoggingService", "utilities": ["structured_logger"]}],
            "data_services": [{"name": "PostgresDataService", "database_type": "postgresql"}],
        },
        "migration_strategy": {
            "migration_phases": [
                {
                    "phase": 1,
                    "name": "Foundation Services",
                    "estimated_duration_weeks": 4,
                    "complexity": "medium",
                    "services": ["LoggingService"],
                    "rationale": "Start with low-risk shared services.",
                    "risks": ["Team ramp-up time"],
                }
            ],
            "implementation_plan": {
                "prerequisites": ["Docker setup"],
                "tools_and_technologies": {"service_mesh": "Istio"},
            },
            "risk_assessment": {
                "high_risks": ["Data consistency across services"],
                "mitigation_strategies": ["Implement saga pattern"],
            },
        },
        "recommendations": ["Adopt API gateway pattern."],
    }


@pytest.fixture
def evaluator(tmp_path: Path) -> MicroserviceArchitectureEvaluator:
    """A real evaluator instance with fake analysis results, no scan needed."""
    instance = MicroserviceArchitectureEvaluator(project_root=tmp_path)
    instance.analysis_results = _fake_analysis_results()
    return instance


def test_markdown_report_renders_real_values_not_placeholders(evaluator: MicroserviceArchitectureEvaluator):
    """Every {expr} in the report tree must have been substituted (#15585)."""
    report = evaluator._generate_markdown_report()

    assert not _LEFTOVER_PLACEHOLDER_RE.search(report), (
        "Report contains an un-substituted {identifier} placeholder -- "
        "a triple-quoted string is missing its f prefix"
    )

    # Executive summary / architecture patterns
    assert "**Analysis Date:** 2026-01-01T00:00:00" in report
    assert "**Total Lines of Code:** 12,345" in report
    assert "**Microservice Readiness Score:** 8/10" in report
    assert "strong" in report  # readiness >= 7 branch of the nested ternary
    assert "**MVC Pattern:** ✅ Present" in report
    assert "**Layered Architecture:** ❌ Not Present" in report

    # Component analysis (helper #1)
    assert "**Total Endpoints:** 42" in report
    assert "`chat_router`: 2 endpoints" in report
    assert "**Total Agents:** 5" in report
    assert "**Chat:** ChatAgent" in report
    assert "**Database Files:** 1" in report
    assert "postgresql, redis" in report
    assert "**Utility Files:** 2" in report

    # Dependency analysis
    assert "`core.orchestrator`: Fan-out(12) + Fan-in(8) = 20" in report
    assert "`autobot_shared.redis_client`: Used by 37 modules" in report
    assert "module_a → module_b → module_a" in report

    # Service boundaries (helper #2)
    assert "#### ChatService" in report
    assert "Because chat is a distinct bounded context." in report
    assert "#### LoggingService" in report
    assert "Provide common logging functionality" in report
    assert "#### PostgresDataService" in report
    assert "Manage postgresql operations" in report

    # Migration strategy
    assert "### Phase 1: Foundation Services" in report
    assert "Start with low-risk shared services." in report
    assert "Docker setup" in report
    assert "**Service Mesh:** Istio" in report
    assert "Data consistency across services" in report
    assert "Implement saga pattern" in report
    assert "1. Adopt API gateway pattern." in report
