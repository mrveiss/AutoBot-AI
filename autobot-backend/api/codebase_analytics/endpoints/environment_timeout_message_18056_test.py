# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The timeout message names the deadline the path actually waited on (#18056).

With the LLM filter the analysis waits LLM_ANALYSIS_TIMEOUT (240 s), but the
message said 120 s, the plain path's deadline.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from api.codebase_analytics.endpoints import environment


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("use_llm_filter", "deadline"),
    [(False, environment.ANALYSIS_TIMEOUT), (True, environment.LLM_ANALYSIS_TIMEOUT)],
)
async def test_the_message_states_the_deadline_of_the_path_taken(use_llm_filter, deadline):
    with patch.object(environment, "_execute_env_analysis", AsyncMock(return_value=None)):
        response = await environment._analyze_and_return_env_result(
            None, "/x", ["p"], use_llm_filter, "model", "all", "src1"
        )
    body = json.loads(response.body)
    assert f"timed out after {deadline}s" in json.dumps(body)
