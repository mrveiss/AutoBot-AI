#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Deleting a chat session cascades to its chat-knowledge context (#16490).

Before this module, ``_perform_all_session_cleanup`` -- the one function
``api/chat_sessions.py``'s ``delete_session`` calls unconditionally, ahead of
deleting the session itself -- cleaned up files, terminal sessions, KB facts
and the conversation transcript, but never the chat-knowledge context living
in ``ChatKnowledgeManager.chat_contexts``. A deleted chat's context, temporary
knowledge and file associations lived on as a permanent orphan.

These tests exercise ``_perform_all_session_cleanup`` itself rather than the
full ``delete_session`` HTTP route: that function is the one place the
cascade must run for every real deletion, so proving it here proves the
route's behaviour without reconstructing its entire auth/audit/hook stack.
"""

import json
from types import SimpleNamespace

import pytest

from api.chat_knowledge_manager import MANAGER_STATE_KEY
from api.chat_sessions import _perform_all_session_cleanup
from api.chat_sessions_delete_cleanup import _cleanup_chat_knowledge_context
from api.schemas_chat import SessionDeleteData

SESSION_ID = "session-16490"


def _manager(**overrides) -> SimpleNamespace:
    """A bare stand-in for ChatKnowledgeManager, same shape used in
    api/chat_knowledge_delete_test.py."""
    defaults = {
        "chat_contexts": {},
        "file_associations": {},
        "pending_decisions": {},
        "storage_dir": "/tmp/unused-chat-knowledge-storage",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _fake_request(chat_knowledge_manager: SimpleNamespace | None = None) -> SimpleNamespace:
    """The minimum ``request.app.state`` surface every cleanup helper reads.

    Every helper ``_perform_all_session_cleanup`` calls resolves its own
    dependency via ``getattr(request.app.state, "...", None)`` and no-ops on
    ``None``, so a bare ``SimpleNamespace`` exercises the real no-op paths
    rather than needing a fake for each one.
    """
    state = SimpleNamespace()
    if chat_knowledge_manager is not None:
        setattr(state, MANAGER_STATE_KEY, chat_knowledge_manager)
    return SimpleNamespace(app=SimpleNamespace(state=state))


class TestCleanupChatKnowledgeContext:
    """Unit-level coverage of the new helper itself."""

    @pytest.mark.asyncio
    async def test_no_manager_ever_built_is_a_no_op(self):
        result = await _cleanup_chat_knowledge_context(_fake_request(), SESSION_ID)

        assert result == {"context_deleted": False, "file_associations_removed": 0}

    @pytest.mark.asyncio
    async def test_a_session_with_no_context_is_a_no_op(self):
        result = await _cleanup_chat_knowledge_context(_fake_request(_manager()), SESSION_ID)

        assert result == {"context_deleted": False, "file_associations_removed": 0}

    @pytest.mark.asyncio
    async def test_deletes_the_session_context_and_reports_it(self):
        manager = _manager(
            chat_contexts={SESSION_ID: object()},
            file_associations={SESSION_ID: [SimpleNamespace(file_path="/tmp/unused-chat-knowledge-storage/x")]},
        )

        result = await _cleanup_chat_knowledge_context(_fake_request(manager), SESSION_ID)

        assert result == {"context_deleted": True, "file_associations_removed": 1}
        assert SESSION_ID not in manager.chat_contexts


class TestSessionDeletionCascadesToChatKnowledge:
    """AC: deleting a chat removes its chat-knowledge context (#16490)."""

    @pytest.mark.asyncio
    async def test_the_context_is_gone_after_cleanup_runs(self):
        manager = _manager(chat_contexts={SESSION_ID: object()})
        request = _fake_request(manager)

        *_other_results, knowledge_context_result = await _perform_all_session_cleanup(
            request, SESSION_ID, "delete", {}
        )

        assert knowledge_context_result["context_deleted"] is True
        assert SESSION_ID not in manager.chat_contexts

    @pytest.mark.asyncio
    async def test_a_session_that_never_touched_chat_knowledge_is_unaffected(self):
        *_other_results, knowledge_context_result = await _perform_all_session_cleanup(
            _fake_request(), SESSION_ID, "delete", {}
        )

        assert knowledge_context_result == {"context_deleted": False, "file_associations_removed": 0}

    @pytest.mark.asyncio
    async def test_the_tuple_still_carries_the_other_four_cleanup_results(self):
        """The new fifth element must not have displaced the existing four."""
        results = await _perform_all_session_cleanup(_fake_request(), SESSION_ID, "delete", {})

        assert len(results) == 5
        file_result, terminal_result, kb_result, transcript_result, _knowledge_context_result = results
        assert file_result["files_handled"] is False
        assert terminal_result["terminal_sessions_closed"] == 0
        assert kb_result["facts_deleted"] == 0
        assert transcript_result["transcript_deleted"] is False


def test_the_cleanup_result_survives_the_response_model():
    """#16502: the handler set the key and ``SessionDeleteData`` did not declare it.

    ``_build_delete_session_response`` has always put the cascade's result under
    ``knowledge_context_cleanup``. The model omitted it and carries no
    ``extra: allow``, so Pydantic's default ``extra="ignore"`` dropped it at
    serialization -- which is the step ``response_model=DataResponse[SessionDeleteData]``
    runs. The caller therefore never learned whether the context was removed,
    while the other four cleanups were reported.

    This asserts the SERIALIZED shape, not the handler's dict. The handler was
    never wrong; a test over its return value would have passed throughout the
    defect.
    """
    payload = {
        "session_id": SESSION_ID,
        "deleted": True,
        "knowledge_context_cleanup": {"context_deleted": True, "file_associations_removed": 3},
    }

    serialized = SessionDeleteData.model_validate(payload).model_dump()

    assert "knowledge_context_cleanup" in serialized, (
        "the key was dropped at serialization -- SessionDeleteData must declare it, "
        "because the model has no `extra: allow` to let an undeclared key through"
    )
    assert serialized["knowledge_context_cleanup"] == {
        "context_deleted": True,
        "file_associations_removed": 3,
    }


def test_an_absent_cleanup_serializes_as_none_rather_than_vanishing():
    """The contrast: the key is present-and-null when the cascade did not run.

    Without this, the assertion above is satisfiable by a model that always
    emits the key regardless of input, which would hide the opposite defect --
    a caller told the context was handled when nothing ran.
    """
    serialized = SessionDeleteData.model_validate({"session_id": SESSION_ID, "deleted": True}).model_dump()

    assert "knowledge_context_cleanup" in serialized
    assert serialized["knowledge_context_cleanup"] is None


def test_the_RESPONSE_BUILDER_emits_the_cleanup_key_not_just_the_model():
    """The producer half. The two tests above validate a payload this test does not write.

    Review on #17911 caught the gap and it is the defect's own shape: both
    assertions above hand ``SessionDeleteData`` a dict that already contains
    ``knowledge_context_cleanup``, so they pass even if ``delete_session`` stops
    emitting it. The field defaults to ``None``, so the route could return
    ``null`` forever with those tests green -- which is exactly how #16502
    survived, a model and a producer each correct about a different half.

    ``_build_delete_session_response`` is pure, so the producer is assertable
    without a live backend: build through it, then validate the result through
    the response model, and the key has to survive both.
    """
    from api.chat_sessions import _build_delete_session_response

    built = _build_delete_session_response(
        session_id=SESSION_ID,
        request_id="req-1",
        file_deletion_result={
            "files_handled": True,
            "action_taken": "deleted",
            "files_deleted": 0,
            "files_transferred": 0,
            "files_failed": 0,
            "error": None,
        },
        terminal_cleanup_result={
            "terminal_sessions_closed": 0,
            "pending_approvals_cleared": 0,
            "error": None,
        },
        kb_cleanup_result={"facts_deleted": 0, "facts_preserved": 0, "cleanup_error": None},
        transcript_cleanup_result={"transcript_deleted": False, "error": None},
        knowledge_context_cleanup_result={"context_deleted": True, "file_associations_removed": 3},
    )

    # `create_chat_response` returns a plain JSONResponse (`utils/chat_utils.py:191`),
    # so the payload must be read out of the body rather than indexed as a dict.
    # That is also WHY the runtime never lost the key: FastAPI does not apply
    # `response_model` to a returned Response object, so the declared model
    # filters nothing here. The defect this issue fixes is in the DECLARED
    # contract -- the OpenAPI schema and the typed SDK client -- not in what the
    # route puts on the wire. See the docstring correction above.
    body = json.loads(built.body.decode("utf-8")) if hasattr(built, "body") else built
    data = body["data"] if isinstance(body, dict) and "data" in body else body
    assert "knowledge_context_cleanup" in data, (
        "the response BUILDER dropped the key -- the model declaring it cannot help if the "
        "producer never puts it in the payload, which is the half #16502 was actually about"
    )

    serialized = SessionDeleteData.model_validate(data).model_dump()
    assert serialized["knowledge_context_cleanup"] == {
        "context_deleted": True,
        "file_associations_removed": 3,
    }, "the builder emitted it and the model dropped it -- the other half of the same defect"
