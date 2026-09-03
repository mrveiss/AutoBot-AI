# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Test for apply_memory_optimizations's markdown report (#15585 sweep finding).

``_generate_markdown_report`` built its header and per-optimization sections
from triple-double-quoted strings containing ``{}`` placeholders with no
``f`` prefix, so ``**Date:**``, ``**Total Optimizations:**`` and each
optimization's title/description rendered their placeholder syntax literally
instead of the real values. This asserts the rendered report contains real
values from the fixture data and no leftover ``{identifier`` placeholder
shape.
"""

import re
import sys
from pathlib import Path

# Lives here, not beside the script it tests -- see microservice_architecture_evaluator_test.py
# in this same directory for the ci.yml path-list reasoning (#14563, #14518).
_SCRIPTS_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from apply_memory_optimizations import MemoryOptimizationApplier  # noqa: E402

_LEFTOVER_PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_]")


def test_markdown_report_renders_real_values_not_placeholders(tmp_path: Path):
    applier = MemoryOptimizationApplier(project_root=tmp_path)
    report_data = {
        "timestamp": "2026-01-01T00:00:00",
        "summary": {"total_optimizations": 2},
        "optimizations_applied": [
            {
                "type": "log_analysis",
                "description": "Reviewed logging verbosity across all services.",
            }
        ],
        "recommendations": ["Enable log rotation for autobot_backend.log."],
    }

    markdown = applier._generate_markdown_report(report_data)

    assert not _LEFTOVER_PLACEHOLDER_RE.search(markdown), (
        "Report contains an un-substituted {identifier} placeholder -- "
        "a triple-quoted string is missing its f prefix"
    )
    assert "**Date:** 2026-01-01T00:00:00" in markdown
    assert "**Total Optimizations:** 2" in markdown
    assert "### Log Analysis" in markdown
    assert "**Description:** Reviewed logging verbosity across all services." in markdown
    assert "Enable log rotation for autobot_backend.log." in markdown
