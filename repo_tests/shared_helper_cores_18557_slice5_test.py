# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The analytics status row of #18557: one home for the code tool probe.

The other ``get_*_status`` routes stay separate: the task routes already share
``known_task_status_or_404``, and the budget, learning, monitoring and pre-commit routes each
return their own payload from their own source.
"""

from __future__ import annotations

import ast

from repo_tests._paths import repo_root

CALLERS = ("autobot-backend/api/analytics.py", "autobot-backend/api/analytics_code.py")
OLD_COPY = "await asyncio.to_thread(analytics_controller.code_index_path.exists)\n"
REBUILT_RESULT = "x = {'code_analysis_suite': a, 'code_index_mcp': b}\n"
TOOL_PATHS = {"code_analysis_path", "code_index_path"}
TOOL_KEYS = {"code_analysis_suite", "code_index_mcp"}
DELEGATE = "await analytics_controller.code_tools_available()\n"


def probes_a_tool_path(source: str) -> bool:
    """True if *source* asks a tool path whether it exists, or builds the probe's result itself."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute) and node.attr == "exists":
            if isinstance(node.value, ast.Attribute) and node.value.attr in TOOL_PATHS:
                return True
        if isinstance(node, ast.Dict) and TOOL_KEYS <= {getattr(key, "value", None) for key in node.keys}:
            return True
    return False


def test_the_detector_flags_an_old_copy_and_passes_a_delegate() -> None:
    assert probes_a_tool_path(OLD_COPY)
    assert probes_a_tool_path(REBUILT_RESULT)
    assert not probes_a_tool_path(DELEGATE)


def test_the_callers_use_the_controller_probe() -> None:
    for rel in CALLERS:
        source = (repo_root() / rel).read_text(encoding="utf-8")
        assert not probes_a_tool_path(source), rel
        assert "code_tools_available" in source, rel
