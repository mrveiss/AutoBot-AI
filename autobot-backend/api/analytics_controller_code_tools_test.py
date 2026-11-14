# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The code tool probe reports each tool from its own path (#18557)."""

import pytest

from api.analytics_controller import AnalyticsController


@pytest.mark.asyncio
@pytest.mark.parametrize(("suite", "index"), [(True, False), (False, True)])
async def test_each_tool_reads_its_own_path(tmp_path, suite, index):
    controller = object.__new__(AnalyticsController)
    controller.code_analysis_path = tmp_path / "suite"
    controller.code_index_path = tmp_path / "index"
    if suite:
        controller.code_analysis_path.mkdir()
    if index:
        controller.code_index_path.mkdir()
    assert await controller.code_tools_available() == {"code_analysis_suite": suite, "code_index_mcp": index}
