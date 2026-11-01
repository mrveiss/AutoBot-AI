# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A chat that used an attachment keeps asking; an admin setting can lift that (#20195).

* The server records, durably, that an attachment turn ran, and stamps every later turn from that record: a later
  turn with no attachment still asks, a chat that never used one does not, a client can neither set nor clear it,
  and it stays true after the file is soft-deleted. An unreadable record asks.
* ``chat.auto_approve_attachment_turns`` (SLM, admin-written, off by default) lifts the floor on attachment turns
  and the later turns of those chats. The normal lines then apply: a stored line 3 still refuses. Each call that
  ran because of it is reported. An unreadable setting asks.
* Attachment turns take the plan-only path whatever the approval-gate flag; other turns follow the flag as before.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from autobot_shared.ai_lines import (
    ATTACHMENT_AUTO_APPROVE_KEY,
    ATTACHMENT_CHAT_KEY,
    ATTACHMENT_TURN_KEY,
    VERIFIED_COMPANY_KEY,
    AiLine,
)
from chat_workflow import approval_baseline, attachment_floor
from chat_workflow.models import LLMIterationContext
from tests.unit.chat_workflow.test_ai_line_support import VERIFIED_COMPANY, ai_line_world, arun_guard

_CALL = {"name": "crm", "params": {"action": "read"}}
_L1 = {"crm:read": AiLine.AUTONOMOUS}


@pytest.fixture
def world(monkeypatch, tmp_path):
    """A REAL conversation files store (temp SQLite); only the SLM setting is faked."""
    from conversation_file_manager import ConversationFileManager

    setting = {"value": None}
    manager = ConversationFileManager(storage_dir=tmp_path / "storage", db_path=tmp_path / "files.db")
    manager._initialize_schema()
    monkeypatch.setattr(manager, "_get_redis_sessions", AsyncMock(side_effect=ConnectionError("down")))

    async def _get():
        return manager

    async def _fetch(key):
        assert key == approval_baseline.AUTO_APPROVE_ATTACHMENTS_SETTING_KEY
        if isinstance(setting["value"], Exception):
            raise setting["value"]
        return setting["value"]

    monkeypatch.setattr("conversation_file_manager.get_conversation_file_manager", _get)
    monkeypatch.setattr(approval_baseline, "fetch_slm_policy_json", _fetch)
    return SimpleNamespace(files=manager, setting=setting)


def _ctx(context=None) -> LLMIterationContext:
    return LLMIterationContext(
        ollama_endpoint="e",
        selected_model="m",
        session_id="s",
        terminal_session_id="t",
        used_knowledge=False,
        rag_citations=[],
        workflow_messages=[],
        context={VERIFIED_COMPANY_KEY: VERIFIED_COMPANY, **(context or {})},
    )


def _stamp(context=None, session="chat-1"):
    return asyncio.run(attachment_floor.stamp_attachment_floor(context, session))


async def _outcome(context, **world):
    message, filed = await arun_guard(_CALL, _ctx(context), [], stored=_L1, **world)
    return message and message.type, filed


# --- the durable record ---------------------------------------------------------------------------------------


def test_a_chat_that_never_used_an_attachment_does_not_ask(world):
    stamped = _stamp({})
    assert ATTACHMENT_CHAT_KEY not in stamped
    assert _ctx(stamped).approve_every_call is False
    assert asyncio.run(_outcome(stamped)) == (None, 0)


def test_a_later_turn_with_no_attachment_still_asks_once_the_chat_used_one(world):
    asyncio.run(attachment_floor.mark_chat("chat-1"))
    later = _stamp({})  # the next turn carries no attachment at all
    assert later[ATTACHMENT_CHAT_KEY] is True and ATTACHMENT_TURN_KEY not in later
    assert _ctx(later).approve_every_call is True
    assert asyncio.run(_outcome(later)) == ("approval_required", 1)
    assert _stamp({}, session="another-chat").get(ATTACHMENT_CHAT_KEY) is None  # per chat, not global


def test_a_client_can_neither_set_nor_clear_the_record(world):
    forged = _stamp({ATTACHMENT_CHAT_KEY: True, ATTACHMENT_AUTO_APPROVE_KEY: True})
    assert ATTACHMENT_CHAT_KEY not in forged and ATTACHMENT_AUTO_APPROVE_KEY not in forged  # never-used chat
    asyncio.run(attachment_floor.mark_chat("chat-1"))
    cleared = _stamp({ATTACHMENT_CHAT_KEY: False, ATTACHMENT_AUTO_APPROVE_KEY: True})
    assert cleared[ATTACHMENT_CHAT_KEY] is True and ATTACHMENT_AUTO_APPROVE_KEY not in cleared
    assert _ctx(cleared).approve_every_call is True


def test_deleting_the_file_through_the_real_route_path_still_asks(world):
    """Mark, then delete the file exactly as the DELETE route does (removes the association): still asks."""

    async def _scenario():
        info = await world.files.add_file("chat-1", b"payload", "doc.txt", uploaded_by="alice")
        await attachment_floor.mark_chat("chat-1")
        assert await world.files.delete_file("chat-1", info["file_id"]) is True
        assert await world.files.get_session_files("chat-1", include_deleted=True) == []  # no row is retained

    asyncio.run(_scenario())
    later = _stamp({})
    assert later[ATTACHMENT_CHAT_KEY] is True and _ctx(later).approve_every_call is True
    assert asyncio.run(_outcome(later)) == ("approval_required", 1)


def test_a_new_chat_marked_on_its_first_turn_needs_no_session_record_or_file_row(world):
    asyncio.run(attachment_floor.mark_chat("brand-new-chat"))  # no session record, no association row exists
    assert _stamp({}, session="brand-new-chat")[ATTACHMENT_CHAT_KEY] is True


def _marked_at(world):
    import sqlite3

    with sqlite3.connect(world.files.db_path) as db:
        return db.execute("SELECT first_marked_at FROM chat_attachment_marks WHERE session_id='chat-1'").fetchall()


def test_marking_twice_keeps_the_first_marked_time(world):
    asyncio.run(attachment_floor.mark_chat("chat-1"))
    first = _marked_at(world)
    assert len(first) == 1
    asyncio.run(attachment_floor.mark_chat("chat-1"))
    assert _marked_at(world) == first


def test_a_store_without_the_table_gains_it_on_the_first_mark_or_read(world):
    import sqlite3

    def _remove_table():
        with sqlite3.connect(world.files.db_path) as db:
            db.execute("ALTER TABLE chat_attachment_marks RENAME TO retired_marks")  # as an older install: no table

    _remove_table()
    assert ATTACHMENT_CHAT_KEY not in _stamp({})  # a read creates it and finds no mark
    with sqlite3.connect(world.files.db_path) as db:
        db.execute("ALTER TABLE chat_attachment_marks RENAME TO retired_marks2")
    asyncio.run(attachment_floor.mark_chat("chat-1"))
    assert _stamp({})[ATTACHMENT_CHAT_KEY] is True


def test_a_failed_durable_write_stops_the_turn_and_reads_no_file(world, monkeypatch):
    from chat_workflow.attachment_context import apply_attachments

    async def _boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr("chat_attachment_marks.write_mark", _boom)
    resolve = AsyncMock()
    with patch("chat_workflow.attachment_context._resolve_turn", resolve):
        with pytest.raises(attachment_floor.AttachmentMarkError, match="could not be saved"):
            asyncio.run(
                apply_attachments(SimpleNamespace(session_id="chat-1"), {"attachments": ["f1"]}, {"prompt": "p"})
            )
    resolve.assert_not_awaited()  # nothing was read


def test_a_turn_naming_only_an_unknown_id_marks_the_chat_though_no_row_exists(world):
    from chat_workflow.attachment_context import apply_attachments

    session = SimpleNamespace(session_id="chat-1")
    asyncio.run(apply_attachments(session, {"attachments": ["no-such-id"]}, {"prompt": "p"}))
    assert _stamp({})[ATTACHMENT_CHAT_KEY] is True


def test_a_chat_that_never_used_an_attachment_does_not_ask_even_with_files_uploaded(world):
    asyncio.run(world.files.add_file("chat-1", b"payload", "doc.txt", uploaded_by="alice"))
    assert ATTACHMENT_CHAT_KEY not in _stamp({}) and asyncio.run(_outcome(_stamp({}))) == (None, 0)


def test_an_unreadable_mark_asks(world, monkeypatch):
    async def _boom(*_a, **_k):
        raise OSError("disk")

    monkeypatch.setattr("chat_attachment_marks.read_mark", _boom)
    assert _stamp({})[ATTACHMENT_CHAT_KEY] is True


def test_the_turn_that_names_a_file_marks_the_chat(world):
    from chat_workflow.attachment_context import apply_attachments

    session = SimpleNamespace(session_id="chat-1")
    asyncio.run(apply_attachments(session, {"attachments": []}, {"prompt": "p"}))
    assert asyncio.run(attachment_floor.chat_used_attachment("chat-1")) is False  # none named: not an attachment turn
    with patch(
        "chat_workflow.attachment_context._resolve_turn", AsyncMock(return_value=SimpleNamespace(block="", notices=[]))
    ):
        asyncio.run(apply_attachments(session, {"attachments": ["f1"]}, {"prompt": "p"}))
    assert asyncio.run(attachment_floor.chat_used_attachment("chat-1")) is True


def test_session_governance_stamps_the_floor_from_the_record(world):
    from chat_workflow.session_role import apply_session_governance

    asyncio.run(attachment_floor.mark_chat("chat-1"))
    with (
        patch("chat_workflow.session_role.SessionRoleService.get_role", AsyncMock(return_value=None)),
        patch("chat_workflow.session_work_item.SessionWorkItemService.get_work_item", AsyncMock(return_value=None)),
    ):
        merged = asyncio.run(apply_session_governance("chat-1", {ATTACHMENT_CHAT_KEY: False}, "user", {}))
    assert merged[ATTACHMENT_CHAT_KEY] is True


def test_a_resumed_turn_gets_the_floor_keys_from_the_server_not_from_its_checkpoint(world):
    from chat_workflow.attachment_context import resume_context

    class _Graph:
        async def aget_state(self, _config):
            return SimpleNamespace(values={"context": {ATTACHMENT_AUTO_APPROVE_KEY: True, "attachments": ["f"]}})

    asyncio.run(attachment_floor.mark_chat("chat-1"))
    update = asyncio.run(resume_context(_Graph(), "chat-1", False))["context"]
    assert update[ATTACHMENT_CHAT_KEY] is True
    assert ATTACHMENT_AUTO_APPROVE_KEY not in update  # the setting is off now: an earlier "on" is not kept
    world.setting["value"] = True
    update = asyncio.run(resume_context(_Graph(), "chat-1", False))["context"]
    assert update[ATTACHMENT_AUTO_APPROVE_KEY] is True


# --- the admin setting ----------------------------------------------------------------------------------------


def test_by_default_an_attachment_turn_and_its_later_turns_ask(world):
    asyncio.run(attachment_floor.mark_chat("chat-1"))
    for context in ({"attachments": ["f"]}, {}):
        stamped = _stamp(context)
        assert ATTACHMENT_AUTO_APPROVE_KEY not in stamped
        assert asyncio.run(_outcome(stamped)) == ("approval_required", 1)


@pytest.mark.parametrize("value", [None, "yes", 1, {"enabled": "true"}, {"on": True}, RuntimeError("slm down")])
def test_an_unset_malformed_or_unreadable_setting_asks(world, value):
    world.setting["value"] = value
    asyncio.run(attachment_floor.mark_chat("chat-1"))
    if isinstance(value, Exception):
        with patch.object(approval_baseline, "fetch_slm_policy_json", AsyncMock(return_value=None)):
            stamped = _stamp({"attachments": ["f"]})  # fetch_slm_policy_json itself turns a failure into None
    else:
        stamped = _stamp({"attachments": ["f"]})
    assert ATTACHMENT_AUTO_APPROVE_KEY not in stamped
    assert _ctx(stamped).approve_every_call is True


@pytest.mark.parametrize("value", [True, {"enabled": True}])
def test_with_the_setting_on_an_attachment_turn_and_a_later_turn_run_without_asking(world, value):
    world.setting["value"] = value
    first = _stamp({"attachments": ["f"], ATTACHMENT_TURN_KEY: True})  # the turn that names a file
    assert first[ATTACHMENT_AUTO_APPROVE_KEY] is True
    assert _ctx(first).approve_every_call is False
    assert asyncio.run(_outcome(first)) == (None, 0)
    asyncio.run(attachment_floor.mark_chat("chat-1"))
    later = _stamp({})
    assert later[ATTACHMENT_CHAT_KEY] is True and later[ATTACHMENT_AUTO_APPROVE_KEY] is True
    assert asyncio.run(_outcome(later)) == (None, 0)


def test_a_chat_that_never_used_an_attachment_gets_no_waiver_key_and_nothing_to_waive(world):
    world.setting["value"] = True
    assert ATTACHMENT_AUTO_APPROVE_KEY not in _stamp({})


def test_a_stored_line_3_still_refuses_with_the_setting_on(world):
    context = {ATTACHMENT_TURN_KEY: True, ATTACHMENT_CHAT_KEY: True, ATTACHMENT_AUTO_APPROVE_KEY: True}
    message, filed = asyncio.run(arun_guard(_CALL, _ctx(context), [], stored=AiLine.NEVER))
    assert message.type == "error" and filed == 0


def test_something_that_asks_for_its_own_reason_still_asks_with_the_setting_on(world):
    context = {ATTACHMENT_CHAT_KEY: True, ATTACHMENT_AUTO_APPROVE_KEY: True}
    # no stored line for a mutating tool: line 2 by the normal rules, nothing to do with attachments
    message, filed = asyncio.run(arun_guard({"name": "crm", "params": {"action": "delete"}}, _ctx(context), []))
    assert message.type == "approval_required" and filed == 1


def test_each_call_that_ran_on_the_setting_is_reported(world):
    audit = AsyncMock(return_value=True)

    async def _run(context):
        with ai_line_world(stored=_L1), patch("services.ai_line_enforcement.audit_log", audit):
            from chat_workflow.tool_dispatch_guards import enforce_ai_line

            return await enforce_ai_line(_CALL, _ctx(context), [])

    waived = {ATTACHMENT_CHAT_KEY: True, ATTACHMENT_AUTO_APPROVE_KEY: True}
    assert asyncio.run(_run(waived)) is None
    assert audit.await_args.kwargs["details"]["attachment_floor_waived"] is True
    assert audit.await_args.args[0] == "ai_line.run"
    assert asyncio.run(_run({})) is None  # an ordinary run is reported without the marker
    assert "attachment_floor_waived" not in audit.await_args.kwargs["details"]


def test_a_non_admin_cannot_change_the_setting():
    """The setting is written only through the SLM settings API, whose every write needs the admin permission."""
    import ast
    from pathlib import Path

    source = Path(__file__).resolve().parents[4] / "autobot-slm-backend" / "api" / "settings.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    writes = {"update_setting", "create_setting", "delete_setting"}
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name in writes:
            found[node.name] = "ADMIN_CONFIG_WRITE" in ast.unparse(node.args)
    assert found == {name: True for name in writes}


# --- the plan-only path ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "flag,context,planned",
    [
        (False, {}, False),  # a turn without attachments follows the flag, exactly as before
        (True, {}, True),
        (False, {ATTACHMENT_TURN_KEY: True}, True),  # an attachment turn is planned whatever the flag
        (False, {ATTACHMENT_CHAT_KEY: True}, True),  # and so is every later turn of that chat
        (False, {ATTACHMENT_TURN_KEY: True, ATTACHMENT_AUTO_APPROVE_KEY: True}, False),  # the setting waives it
        (True, {ATTACHMENT_TURN_KEY: True, ATTACHMENT_AUTO_APPROVE_KEY: True}, True),  # the flag still decides
    ],
)
def test_generate_response_takes_the_plan_only_path_by_the_flag_or_the_attachment_floor(
    monkeypatch, flag, context, planned
):
    from chat_workflow import graph, session_role

    ctx = _ctx(context)
    inline = AsyncMock(return_value=([], "reply", False))
    plan = AsyncMock(return_value={"planned": True})
    monkeypatch.setattr(session_role, "CHAT_APPROVAL_GATE_ENABLED", flag)
    monkeypatch.setattr(graph, "_build_llm_iteration_context", lambda _state: ctx)
    monkeypatch.setattr(graph, "_run_llm_iteration", inline)
    monkeypatch.setattr(graph, "_generate_response_planned", plan)
    state = {"session_id": "s", "user_message": "m", "iteration_count": 0}
    result = asyncio.run(graph.generate_response(state, {"configurable": {"manager": object()}}))
    assert plan.await_count == int(planned) and inline.await_count == int(not planned)
    assert (result == {"planned": True}) is planned
