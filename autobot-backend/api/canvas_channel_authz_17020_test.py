# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`canvas:{id}` is gated on the canvas's owner, and fails closed (#17020).

The canvas channel is new: `useCanvasWebSocket` used to open a bespoke
`/api/canvas/{id}/ws` that the backend never served, so nothing was ever
authorized because nothing was ever delivered. Publishing on a channel makes
authorization load-bearing for the first time.

The rule is the one `api/canvas.py` applies to every REST route on the resource
-- `canvas.user_id == caller` -- asked here rather than re-derived, so the two
surfaces cannot drift into disagreeing about who may see a canvas.

`EVENT_STATE_DOCTRINE` lists "fail closed on channel authorization" as a rule
with teeth: an unknown or unowned resource is a denial, not an absence of
restriction. The unreadable-store and raising-lookup cases below are that rule,
and they are the ones a happy-path test would miss.
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.live_events import _authorize_canvas_channel


@asynccontextmanager
async def _fake_session_cm(canvas):
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=canvas)
    session.execute = AsyncMock(return_value=result)
    yield session


def _patch_session(canvas):
    factory = MagicMock(return_value=_fake_session_cm(canvas))
    return patch("user_management.database.get_async_session_factory", MagicMock(return_value=factory))


def _canvas(user_id: str):
    owned = MagicMock()
    owned.user_id = user_id
    return owned


@pytest.mark.asyncio
async def test_the_owner_is_admitted() -> None:
    with _patch_session(_canvas("u1")):
        assert await _authorize_canvas_channel("canvas:cv1", {"user_id": "u1", "roles": []}) is True


@pytest.mark.asyncio
async def test_another_user_is_refused() -> None:
    """The reason the channel needs a check at all: without it, any authenticated
    client could read any user's canvas by naming its id."""
    with _patch_session(_canvas("someone-else")):
        assert await _authorize_canvas_channel("canvas:cv1", {"user_id": "u1", "roles": []}) is False


@pytest.mark.asyncio
async def test_an_unknown_canvas_is_refused_not_ignored() -> None:
    with _patch_session(None):
        assert await _authorize_canvas_channel("canvas:cv1", {"user_id": "u1", "roles": []}) is False


@pytest.mark.asyncio
async def test_a_raising_lookup_refuses() -> None:
    """Fail closed. An error resolving ownership must not read as "no restriction"."""
    factory = MagicMock(side_effect=RuntimeError("store down"))
    with patch("user_management.database.get_async_session_factory", MagicMock(return_value=factory)):
        assert await _authorize_canvas_channel("canvas:cv1", {"user_id": "u1", "roles": []}) is False


@pytest.mark.asyncio
async def test_an_empty_id_is_refused() -> None:
    assert await _authorize_canvas_channel("canvas:", {"user_id": "u1", "roles": []}) is False


@pytest.mark.asyncio
async def test_a_caller_with_no_identity_is_refused() -> None:
    assert await _authorize_canvas_channel("canvas:cv1", {"roles": []}) is False


@pytest.mark.asyncio
async def test_admin_bypasses_ownership_as_on_every_other_prefix() -> None:
    """Consistency, not a widening: `agent:`, `company:` and the resource
    prefixes all let an admin through, and a canvas channel that did not would
    be the odd one out rather than the safe one."""
    assert await _authorize_canvas_channel("canvas:cv1", {"roles": ["admin"], "user_id": "someone"}) is True


@pytest.mark.asyncio
async def test_the_username_serves_when_no_user_id_is_present() -> None:
    """`api/canvas.py:_user_id` falls back through user_id -> id -> username, so a
    canvas owned under a username must still authorize its owner."""
    with _patch_session(_canvas("alice")):
        assert await _authorize_canvas_channel("canvas:cv1", {"username": "alice", "roles": []}) is True
