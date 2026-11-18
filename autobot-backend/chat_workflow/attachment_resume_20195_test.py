# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Resuming a paused turn consults the chat's durable attachment mark, not only the checkpoint (#20195)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.chat_streaming import attachments_allowed, resume_attachment_verdict


def _verdict(*, strict, checkpoint, marked):
    with (
        patch("api.chat_streaming.attachments_allowed", AsyncMock(return_value=strict)),
        patch("chat_workflow.attachment_context.checkpoint_carries_floor", AsyncMock(return_value=checkpoint)),
        patch("chat_workflow.attachment_floor.chat_used_attachment", AsyncMock(return_value=marked)),
    ):
        return asyncio.run(resume_attachment_verdict(MagicMock(), "chat-1", {"username": "bob"}, MagicMock()))


def test_a_checkpoint_older_than_the_mark_still_needs_the_strict_check_once_the_chat_is_marked():
    with pytest.raises(HTTPException) as refused:
        _verdict(strict=False, checkpoint=False, marked=True)  # the checkpoint predates the stamp
    assert refused.value.status_code == 404


def test_an_unmarked_chat_with_an_unstamped_checkpoint_keeps_the_default_posture():
    assert _verdict(strict=False, checkpoint=False, marked=False) is False


def test_the_strict_owner_resumes_a_marked_chat():
    assert _verdict(strict=True, checkpoint=False, marked=True) is True


def test_a_global_admin_passes_strict_on_a_chat_with_no_recorded_owner_without_asking_for_one():
    owner = AsyncMock(side_effect=AssertionError("an admin is not matched against an owner"))
    with patch("security.session_posture.read_owner", owner):
        allowed = asyncio.run(attachments_allowed("chat-1", {"username": "root", "role": "admin"}, MagicMock()))
    assert allowed is True


def test_a_user_on_a_chat_with_no_recorded_owner_is_refused_and_the_paused_turn_waits_for_an_admin():
    gone = HTTPException(status_code=404, detail="Chat session not found")
    user = {"username": "bob", "role": "user"}
    with (
        patch("security.session_posture.read_owner", AsyncMock(return_value=None)),
        patch("security.session_posture.unowned_access", AsyncMock(side_effect=gone)),
    ):
        assert asyncio.run(attachments_allowed("chat-1", user, MagicMock())) is False
        with (
            patch("chat_workflow.attachment_context.checkpoint_carries_floor", AsyncMock(return_value=True)),
            pytest.raises(HTTPException) as refused,
        ):
            asyncio.run(resume_attachment_verdict(MagicMock(), "chat-1", user, MagicMock()))
    assert refused.value.status_code == 404
