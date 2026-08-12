# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""`send_to_browser_vm` validates untrusted URLs, and only untrusted ones (#13204).

The gap: this helper performed **no** URL validation and is reachable from the
agent tool path — `chat_workflow/tool_handler.py` forwards a model-chosen
`tool_name` with model-supplied `params`, so a navigate URL could travel from
the model to the browser worker unchecked. `is_url_allowed` guarded exactly one
HTTP endpoint, and is a regex over the string, so it cannot see where a host
resolves.

The guard sits at the transport because that is the one place every current and
future caller passes through — a new call site cannot reintroduce the gap.

The admin `/browser/mcp/*` endpoints opt out on purpose. They are behind
`check_admin_permission` and rate limiting, and reaching internal hosts is the
point of them: pointing the browser at an internal service and reading what the
page requests is how wrong API calls get found. These tests pin **both** halves,
because a later edit could plausibly break either.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.browser_mcp import _reject_non_public_url, send_to_browser_vm

_GUARD = "api.browser_mcp.is_public_url_async"


@pytest.mark.asyncio
async def test_navigate_to_a_non_public_url_is_refused():
    """The agent path: a model-supplied URL must not reach the worker."""
    with patch(_GUARD, AsyncMock(return_value=False)):
        with pytest.raises(HTTPException) as excinfo:
            await send_to_browser_vm("navigate", {"url": "http://169.254.169.254/latest/meta-data/"})

    assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_a_refused_url_never_reaches_the_transport():
    """Raising after the POST would be no guard at all."""
    with patch(_GUARD, AsyncMock(return_value=False)):
        with patch("api.browser_mcp.get_http_client") as http:
            with pytest.raises(HTTPException):
                await send_to_browser_vm("navigate", {"url": "http://127.0.0.1:6379/"})

    http.assert_not_called()


@pytest.mark.asyncio
async def test_actions_without_a_url_are_not_blocked():
    """Only `navigate` carries a URL; selectors and scripts must pass through."""
    with patch(_GUARD, AsyncMock(return_value=False)) as guard:
        await _reject_non_public_url({"selector": "#submit"})
        await _reject_non_public_url({"script": "return 1"})
        await _reject_non_public_url({"index": 3})
        await _reject_non_public_url({})

    guard.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_public_url_passes_the_guard():
    with patch(_GUARD, AsyncMock(return_value=True)) as guard:
        await _reject_non_public_url({"url": "https://example.com/"})

    guard.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_surface_may_still_reach_internal_hosts():
    """internal_ok=True is how the admin endpoints keep working.

    Removing this exemption would break the diagnostic use the surface exists
    for — driving the browser at an internal service to see what it requests.
    """
    reached_transport = RuntimeError("reached the transport")

    with patch(_GUARD, AsyncMock(return_value=False)) as guard:
        with patch("api.browser_mcp.get_http_client", side_effect=reached_transport):
            # Getting as far as the transport is the assertion: with the guard
            # active this would have raised 403 before ever calling it.
            with pytest.raises(RuntimeError, match="reached the transport"):
                await send_to_browser_vm(
                    "navigate",
                    {"url": "http://localhost:3000/"},
                    internal_ok=True,
                )

    guard.assert_not_awaited()


def test_the_guard_defaults_to_enforced():
    """A new caller that forgets the flag must be guarded, not exempt."""
    import inspect

    sig = inspect.signature(send_to_browser_vm)
    param = sig.parameters["internal_ok"]

    assert param.default is False
    assert param.kind is inspect.Parameter.KEYWORD_ONLY, "must be explicit at the call site"


def test_only_the_admin_endpoints_opt_out():
    """The agent path must never pass internal_ok."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[3]
    tool_handler = (root / "chat_workflow/tool_handler.py").read_text(encoding="utf-8")

    assert "internal_ok" not in tool_handler, "the agent tool path must stay guarded"
