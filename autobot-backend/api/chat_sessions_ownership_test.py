# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Session endpoints must refuse a session the caller does not own (#14011).

Two gaps, both found by reading every endpoint in `api/chat_sessions.py` rather
than grepping for the word "ownership":

- ``export_session`` returned another user's **entire transcript**. It even
  audit-logged the export, so the disclosure was recorded and not prevented.
- ``reset_chat`` took ``session_id`` from the request body and cleared another
  user's conversation.

The tests assert behaviour. The precedent in this repo
(`api_endpoint_migrations_test.py`) uses ``inspect.getsource`` + ``assertIn``,
which passes on a check that is present but never reached — the failure mode
worth guarding against when the whole defect is "the call was missing".
"""

import contextlib
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api import chat_sessions


def _forbidden(*_args, **_kwargs):
    raise HTTPException(status_code=403, detail="not your session")


class TestExportRequiresOwnership:
    """A path-parameter endpoint, so it uses this file's `Depends` pattern."""

    def test_the_dependency_is_declared(self):
        """`Depends` is resolved by FastAPI, so the wiring is what there is to assert.

        Calling the function directly would bypass dependency resolution
        entirely and prove nothing — hence a signature assertion here, and a
        behavioural one for `reset_chat` below, which calls its check inline.
        """
        params = inspect.signature(chat_sessions.export_session).parameters

        assert "ownership" in params, "export_session must declare the ownership dependency"
        assert params["ownership"].default is not inspect.Parameter.empty

    def test_the_dependency_is_the_canonical_validator(self):
        """A `Depends` on some other callable would look identical in the signature."""
        dep = inspect.signature(chat_sessions.export_session).parameters["ownership"].default

        assert dep.dependency is chat_sessions.validate_session_ownership


class TestResetRequiresOwnership:
    @pytest.mark.asyncio
    async def test_a_non_owner_cannot_reset_someone_elses_session(self):
        request = MagicMock()
        reset = MagicMock(session_id="someone-elses-chat", clear_context=True, keep_system_prompt=True)

        with patch.object(chat_sessions, "validate_session_ownership", side_effect=_forbidden):
            with patch.object(chat_sessions, "get_chat_history_manager", MagicMock()):
                with pytest.raises(HTTPException) as excinfo:
                    await chat_sessions.reset_chat(request, reset)

        assert excinfo.value.status_code == 403

    @pytest.mark.asyncio
    async def test_the_refusal_happens_before_the_session_is_cleared(self):
        """A check that runs after the wipe is not a check."""
        manager = MagicMock()
        manager.save_session = AsyncMock()
        manager.clear_session = AsyncMock()
        request = MagicMock()
        reset = MagicMock(session_id="someone-elses-chat", clear_context=True, keep_system_prompt=True)

        with patch.object(chat_sessions, "validate_session_ownership", side_effect=_forbidden):
            with patch.object(chat_sessions, "get_chat_history_manager", MagicMock(return_value=manager)):
                with pytest.raises(HTTPException):
                    await chat_sessions.reset_chat(request, reset)

        manager.save_session.assert_not_awaited()
        manager.clear_session.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_validated_session_id_is_the_one_from_the_body(self):
        """The body-vs-path mismatch that makes `Depends` unusable here."""
        seen = {}

        async def _record(session_id, request):  # noqa: ARG001
            seen["session_id"] = session_id
            raise HTTPException(status_code=403, detail="stop here")

        request = MagicMock()
        reset = MagicMock(session_id="chat-from-the-body", clear_context=True, keep_system_prompt=True)

        with patch.object(chat_sessions, "validate_session_ownership", _record):
            with patch.object(chat_sessions, "get_chat_history_manager", MagicMock()):
                with pytest.raises(HTTPException):
                    await chat_sessions.reset_chat(request, reset)

        assert seen["session_id"] == "chat-from-the-body"

    @pytest.mark.asyncio
    async def test_a_reset_with_no_session_id_is_not_gated(self):
        """An absent id mints a new session — there is no owner to check yet.

        Gating it would break starting a fresh chat, so this pins that the new
        guard is scoped to the case that actually has an owner.
        """
        checked = MagicMock(side_effect=AssertionError("must not gate a session-less reset"))
        request = MagicMock()
        reset = MagicMock(session_id=None, clear_context=True, keep_system_prompt=True)

        with patch.object(chat_sessions, "validate_session_ownership", checked):
            with patch.object(chat_sessions, "get_chat_history_manager", MagicMock(return_value=None)):
                # Whatever else this path does is not under test; the assertion is
                # that the ownership guard was never consulted.
                with contextlib.suppress(Exception):
                    await chat_sessions.reset_chat(request, reset)

        checked.assert_not_called()
