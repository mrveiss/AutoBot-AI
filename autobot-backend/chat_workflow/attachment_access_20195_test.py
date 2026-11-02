# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Who may have a file's text in an answer, and what may outlive the turn that read it (#20195).

* The chat route applies the STRICT session posture (``validate_strict``: admin, or the recorded owner by
  username) before any attachment is read; ``apply_attachments`` reads nothing without that verdict.
* Graph state is checkpointed to Redis (30 days by default), so file text stays out of it and is re-resolved
  per turn: a soft-deleted file no longer reaches a later turn.
* Reads are bounded BEFORE extraction: file size, an archive's declared uncompressed size, a timeout.
"""

# flake8: noqa: F811 -- fixtures imported from the sibling test module are redefined as test arguments

from __future__ import annotations

import asyncio
import io
import json
import zipfile
from types import SimpleNamespace

import pytest

from api.chat_streaming import attach_scope
from autobot_shared.ai_lines import VERIFIED_ATTACHMENT_ACCESS_KEY
from chat_workflow import attachment_context, limits
from chat_workflow.attachment_context_20195_test import _ALICE, _BASE, _FACT, _codes, _seed, _turn, world  # noqa: F401
from chat_workflow.session_role import apply_auth_role

_OWNER = {"username": "alice", "role": "user", "org_id": "org-1"}


class _History:
    def __init__(self, owner):
        self.owner = owner

    async def get_session_owner(self, _session_id):
        if isinstance(self.owner, Exception):
            raise self.owner
        return self.owner


@pytest.fixture
def strict_world(monkeypatch):
    """The real ``validate_strict``; the recorded owner is whatever the test sets. Flags and shares are tripwires."""

    def _scope(user, owner="alice", attachments=("x",)):
        monkeypatch.setattr("utils.chat_utils.get_chat_history_manager", lambda request: _History(owner))
        request = SimpleNamespace(method="POST")
        return asyncio.run(attach_scope(user, "chat-1", request, {"attachments": list(attachments)}))

    def _tripwire(*_a, **_k):
        raise AssertionError("the STRICT posture must not consult flags, shares or org grants")

    monkeypatch.setattr("services.feature_flags.get_feature_flags", _tripwire)
    monkeypatch.setattr("security.session_ownership.SessionOwnershipValidator.is_shared_with_user", _tripwire)
    return _scope


def test_the_recorded_owner_and_a_global_admin_pass(strict_world):
    assert strict_world(_OWNER)["attachment_access"] is True
    assert strict_world({"username": "root", "role": "admin"})["attachment_access"] is True


@pytest.mark.parametrize(
    "caller",
    [
        {"username": "bob", "role": "user", "org_id": "org-1"},  # holds a share of the session / DEFAULT would pass
        {"username": "olga", "role": "org_admin", "org_id": "org-1"},  # an org admin of the owner's org
        {"username": "bob", "role": "editor"},  # a log_only or degraded rollout passes everyone under DEFAULT
    ],
    ids=["shared-session-user", "org-admin", "log-only-caller"],
)
def test_anyone_else_is_refused_even_when_the_default_posture_would_pass_them(strict_world, caller):
    assert strict_world(caller)["attachment_access"] is False


def test_failures_and_unowned_sessions_fail_closed(strict_world):
    user = {"username": "bob", "role": "user"}
    assert strict_world(user, owner=RuntimeError("store down"))["attachment_access"] is False
    assert strict_world(user, owner=None)["attachment_access"] is False
    assert strict_world({"username": "bob"})["attachment_access"] is False  # no role at all


def test_a_turn_that_names_no_attachment_never_runs_the_check(strict_world):
    assert strict_world(_OWNER, attachments=())["attachment_access"] is False


def test_the_verdict_is_overlaid_by_the_server_and_a_client_forged_one_is_stripped():
    forged = {VERIFIED_ATTACHMENT_ACCESS_KEY: True}
    assert VERIFIED_ATTACHMENT_ACCESS_KEY not in apply_auth_role(forged, "user", {"user_id": "u"})
    assert apply_auth_role({}, "user", {"attachment_access": True})[VERIFIED_ATTACHMENT_ACCESS_KEY] is True


def test_a_holder_of_a_file_id_without_the_verdict_gets_nothing(world):
    file_id = _seed(world, _ALICE, "report.txt", _FACT.encode())
    params, prompt = _turn(world, [file_id], authorized=False)
    assert _FACT not in prompt and prompt == _BASE and _codes(params) == ["unavailable"]


def test_a_soft_deleted_file_reaches_neither_an_answer_nor_a_preview(world):
    file_id = _seed(world, _ALICE, "report.txt", _FACT.encode())
    assert _FACT in _turn(world, [file_id])[1]
    assert asyncio.run(world.files.delete_session_files(_ALICE)) == 1  # soft: the row is flagged, bytes stay
    params, prompt = _turn(world, [file_id])
    assert _FACT not in prompt and _codes(params) == ["unavailable"]
    assert asyncio.run(world.files.get_file_info(_ALICE, file_id)) is None  # the preview route's lookup


def test_a_later_graph_turn_re_resolves_so_a_file_deleted_mid_conversation_no_longer_reaches_it(world):
    file_id = _seed(world, _ALICE, "report.txt", _FACT.encode())
    chat = world.chat
    chat.get_or_create_session = _async(SimpleNamespace(session_id=_ALICE, metadata={}))
    context = {"attachments": [file_id], "verified_user_id": "alice", VERIFIED_ATTACHMENT_ACCESS_KEY: True}
    ctx = SimpleNamespace(session_id=_ALICE, context=context, selected_model="m", initial_prompt=_BASE)
    restored = asyncio.run(attachment_context.attachment_prompt(chat, ctx))
    assert _FACT in restored and restored.endswith(_BASE)
    asyncio.run(world.files.delete_session_files(_ALICE))
    assert asyncio.run(attachment_context.attachment_prompt(chat, ctx)) == _BASE
    context.pop(VERIFIED_ATTACHMENT_ACCESS_KEY)  # a resumed turn whose verdict is gone reads nothing
    assert asyncio.run(attachment_context.attachment_prompt(chat, ctx)) == _BASE


def _async(value):
    async def _f(*_a, **_k):
        return value

    return _f


def test_an_oversize_file_is_refused_before_any_reader_opens_it(world, monkeypatch):
    monkeypatch.setattr(limits, "ATTACHMENT_MAX_FILE_BYTES", 100)
    file_id = _seed(world, _ALICE, "big.txt", b"x" * 500 + _FACT.encode())

    async def _never(*_a, **_k):
        raise AssertionError("extraction must not start")

    monkeypatch.setattr(world.files, "get_file_content", _never)
    params, prompt = _turn(world, [file_id])
    assert _FACT not in prompt and _codes(params) == ["over_budget"]


def _bomb() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", "A" * 200_000)  # tiny on disk, large declared
    return buffer.getvalue()


def test_an_archive_that_declares_too_much_is_refused_without_being_opened(world, monkeypatch):
    monkeypatch.setattr(limits, "ATTACHMENT_MAX_UNCOMPRESSED_BYTES", 10_000)
    file_id = _seed(world, _ALICE, "bomb.docx", _bomb(), mime="application/octet-stream")
    from utils.document_parser import DocumentParser

    async def _never(*_a, **_k):
        raise AssertionError("the parser must not open a bomb")

    monkeypatch.setattr(DocumentParser, "extract_text", _never)
    params, prompt = _turn(world, [file_id])
    assert prompt == _BASE and _codes(params) == ["over_budget"]


def test_an_extraction_that_hangs_is_cut_off_and_reported(world, monkeypatch):
    monkeypatch.setattr(limits, "ATTACHMENT_EXTRACT_TIMEOUT_SECONDS", 0.2)
    file_id = _seed(world, _ALICE, "slow.txt", _FACT.encode())

    async def _hang(*_a, **_k):
        await asyncio.sleep(30)

    monkeypatch.setattr(world.files, "get_file_content", _hang)
    params, prompt = _turn(world, [file_id])
    assert prompt == _BASE and _codes(params) == ["unreadable"]


def test_nothing_in_the_log_carries_file_text(world, caplog):
    file_id = _seed(world, _ALICE, "report.txt", _FACT.encode())
    with caplog.at_level("DEBUG"):
        _turn(world, [file_id], authorized=False)
        _turn(world, [file_id])
    assert _FACT not in json.dumps([r.getMessage() for r in caplog.records])
