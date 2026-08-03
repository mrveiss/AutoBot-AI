# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Browser-tool policy-block messages are friendly, not raw errors (#10914).

A disallowed navigate URL or unsafe script is an *expected* policy outcome. The
validator must return user-friendly notice text (no raw ``URL not allowed:``),
and the handler surfaces it as a ``tool_result`` — not a scary ``error`` banner.
"""

from unittest.mock import AsyncMock, patch

import pytest

from chat_workflow.tool_handler import ToolHandlerMixin

# _validate_browser_params does not use instance state — call it unbound.
_validate = ToolHandlerMixin._validate_browser_params
_SELF = object()


@pytest.mark.asyncio
async def test_navigate_block_is_friendly_not_raw() -> None:
    # #13236 step 5: is_url_allowed resolves the host, so it is async now.
    with patch("api.browser_mcp.is_url_allowed", AsyncMock(return_value=False)):
        msg = await _validate(_SELF, "navigate", {"url": "https://colorlib.com/x/#adminlte-4"})
    assert msg is not None
    assert "URL not allowed" not in msg  # no raw error string
    assert "can't open that link" in msg.lower()
    assert "https://colorlib.com/x/#adminlte-4" in msg  # still names the URL


@pytest.mark.asyncio
async def test_unsafe_script_block_is_friendly() -> None:
    with patch("api.browser_mcp.is_script_safe", return_value=False):
        msg = await _validate(_SELF, "evaluate", {"script": "while(true){}"})
    assert msg is not None
    assert "blocked by the security policy" in msg.lower()
    assert "JavaScript blocked" not in msg  # not the old raw text


@pytest.mark.asyncio
async def test_allowed_navigate_returns_none() -> None:
    with patch("api.browser_mcp.is_url_allowed", AsyncMock(return_value=True)):
        assert await _validate(_SELF, "navigate", {"url": "https://github.com"}) is None
