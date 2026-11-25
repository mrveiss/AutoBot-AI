# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#22016 PR1: the prompt budget is the window the request sends, and a cut file is reported honestly."""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from autobot_shared import chat_model_context
from autobot_shared.ai_lines import VERIFIED_ATTACHMENT_ACCESS_KEY, VERIFIED_USER_KEY
from autobot_shared.ssot_constants import ModelConfig
from chat_workflow import attachment_context, prompt_window
from context_window_manager import get_context_window_manager

MODEL = "chat-model-22016"
SYSTEM = "S" * 11_000  # the real simple system prompt is about 11 KB
BASE = "history and question " * 100


@pytest.fixture
def chat_model(monkeypatch):
    monkeypatch.setattr(chat_model_context, "_last_turn_model", MODEL)
    return MODEL


@pytest.fixture
def fake_file(monkeypatch):
    manager = SimpleNamespace(get_file_info=AsyncMock(return_value={"original_filename": "big.txt"}))
    monkeypatch.setattr(attachment_context, "_file_manager", AsyncMock(return_value=manager))
    monkeypatch.setattr(attachment_context, "_read_text", AsyncMock(return_value="word " * 4000))  # 20k chars
    monkeypatch.setattr(attachment_context.attachment_floor, "mark_chat", AsyncMock())


async def _turn(prompt_text=BASE):
    params = {"model": MODEL, "prompt": prompt_text, "system_prompt": SYSTEM}
    ctx = {"attachments": ["f1"], VERIFIED_USER_KEY: "u", VERIFIED_ATTACHMENT_ACCESS_KEY: True}
    await attachment_context.apply_attachments(SimpleNamespace(session_id="s"), ctx, params)
    return params


@pytest.mark.asyncio
async def test_chat_model_with_a_20k_char_attachment_fits_the_window_it_sends(chat_model, fake_file):
    cwm = get_context_window_manager()
    params = await _turn()
    sent = cwm.estimate_tokens(params["system_prompt"]) + cwm.estimate_tokens(params["prompt"])
    assert sent + prompt_window.output_reserve_tokens(cwm, MODEL) <= ModelConfig.CHAT_NUM_CTX  # fails on main
    assert "PARTIAL: only the first" in params["prompt"]  # the model is told the text is partial


@pytest.mark.asyncio
async def test_truncated_notice_carries_used_and_total_chars(chat_model, fake_file):
    params = await _turn()
    (notice,) = [n for n in params["attachment_notices"] if n["metadata"]["code"] == "truncated"]
    meta = notice["metadata"]
    assert meta["total"] == 19_999 and 0 < meta["used"] < meta["total"]
    assert f"{meta['used']} of {meta['total']}" in notice["content"]


def test_window_is_what_the_request_sends_and_reply_reserve_is_2048(chat_model):
    cwm = get_context_window_manager()
    assert prompt_window.request_window_tokens(cwm, MODEL) == ModelConfig.CHAT_NUM_CTX == 8192
    assert prompt_window.output_reserve_tokens(cwm, MODEL) == 2048


def test_budget_applies_the_safety_margin_and_measures_the_system_prompt(chat_model):
    cwm = get_context_window_manager()
    margin = cwm.config["token_estimation"]["safety_margin"]
    base = prompt_window.prompt_budget_tokens(cwm, MODEL)
    assert base <= int(8192 * margin) - 2048
    measured = prompt_window.measured_prompt_budget(cwm, MODEL, SYSTEM)
    assert measured == base - (cwm.estimate_tokens(SYSTEM) - 500)


def test_over_window_notice_only_when_the_prompt_cannot_fit(chat_model):
    big = {"model": MODEL, "prompt": "x" * 40_000, "system_prompt": SYSTEM}
    (notice,) = attachment_context._window_notice(big, None)
    assert notice["metadata"]["code"] == "over_window" and notice["metadata"]["window"] == 8192
    assert attachment_context._window_notice({"model": MODEL, "prompt": "hi", "system_prompt": "sys"}, None) == []


class _Manager:
    """Hands every caller the same session, as the real manager does within a turn."""

    def __init__(self):
        self.session = SimpleNamespace(session_id="s", metadata={})

    async def get_or_create_session(self, session_id):
        return self.session


def _call(prompt, context=None, system=SYSTEM, manager=None):
    ctx = SimpleNamespace(selected_model=MODEL, system_prompt=system, session_id="s", context=context)
    return SimpleNamespace(ctx=ctx, prompt=prompt, manager=manager or _Manager())


@pytest.mark.asyncio
async def test_send_point_notices_once_per_turn_when_the_prompt_is_over_the_window(chat_model, caplog, monkeypatch):
    monkeypatch.setattr(attachment_context, "persist_notices", AsyncMock())
    call = _call("x" * 40_000, context={})
    with caplog.at_level(logging.WARNING):
        (notice,) = await attachment_context.send_point_notices(call)
    assert "input will be cut" in caplog.text and notice.metadata["code"] == "over_window"
    assert await attachment_context.send_point_notices(call) == []  # the next iteration of the turn stays quiet
    assert await attachment_context.send_point_notices(_call("hi", system="sys")) == []  # fits: no notice


@pytest.mark.asyncio
async def test_send_point_check_reads_its_arguments_inside_the_try(chat_model):
    assert await attachment_context.send_point_notices(SimpleNamespace()) == []  # no .ctx: must not raise


def test_prompt_eval_count_at_the_window_is_logged(chat_model, caplog):
    with caplog.at_level(logging.WARNING):
        assert prompt_window.note_prompt_eval({"done": True, "prompt_eval_count": 8192}, MODEL) is True
    assert "reached the window" in caplog.text
    assert prompt_window.note_prompt_eval({"done": True, "prompt_eval_count": 900}, MODEL) is False
    assert prompt_window.note_prompt_eval({"done": False, "prompt_eval_count": 8192}, MODEL) is False


def test_any_ollama_bound_model_gets_the_sent_window_on_a_fresh_process(monkeypatch):
    """A non-default model, nothing noted as the chat model: the payload still sends CHAT_NUM_CTX, so the budget uses it."""
    monkeypatch.setattr(chat_model_context, "_last_turn_model", None)
    cwm = get_context_window_manager()
    assert prompt_window.request_window_tokens(cwm, "some-other-model:7b") == ModelConfig.CHAT_NUM_CTX
    assert prompt_window.chat_request_options("some-other-model:7b")["num_ctx"] == ModelConfig.CHAT_NUM_CTX


def test_budget_window_and_payload_num_ctx_are_the_same_function(chat_model):
    cwm = get_context_window_manager()
    options = prompt_window.chat_request_options(MODEL)
    assert options["num_ctx"] == prompt_window.request_window_tokens(cwm, MODEL) == chat_model_context.sent_num_ctx()


def test_the_payload_sends_the_reply_reserve_as_num_predict(chat_model):
    from chat_workflow.manager import ChatWorkflowManager

    cwm = get_context_window_manager()
    options = ChatWorkflowManager._get_llm_request_payload(object.__new__(ChatWorkflowManager), MODEL, "p", "s")[
        "options"
    ]
    assert options["num_predict"] == prompt_window.output_reserve_tokens(cwm, MODEL) == 2048
    assert options["num_ctx"] == 8192 and options["temperature"] == 0.7 and options["top_p"] == 0.9


def test_a_failover_hop_gets_the_hop_models_declared_window_not_the_sent_one():
    cwm = get_context_window_manager()
    declared = cwm.get_adaptive_context_length("hop-model")
    assert prompt_window.request_window_tokens(cwm, "hop-model", hop=True) == declared


@pytest.mark.asyncio
async def test_a_hop_into_a_smaller_window_notifies_with_the_hop_windows_reserve_and_budget(chat_model, monkeypatch):
    cwm = get_context_window_manager()
    monkeypatch.setattr(attachment_context, "persist_notices", AsyncMock())
    real = cwm.get_adaptive_context_length
    monkeypatch.setattr(cwm, "get_adaptive_context_length", lambda m=None: 4096 if m == "hop-model" else real(m))
    prompt = "x" * 14_000  # about 3,500 tokens: fits 8,192 with its reserve, not the hop's 4,096
    call = _call(prompt, system="sys")
    assert await attachment_context.send_point_notices(call) == []  # the sent window holds it
    (notice,) = await attachment_context.send_point_notices(call, "hop-model", hop=True)
    assert notice.metadata["code"] == "over_window" and notice.metadata["window"] == 4096
    assert prompt_window.output_reserve_tokens(cwm, "hop-model", hop=True) == 1024  # 25% of the HOP window
    assert prompt_window.measured_prompt_budget(cwm, "hop-model", "sys", hop=True) <= int(4096 * 0.9) - 1024
    assert await attachment_context.send_point_notices(call, "hop-model", hop=True) == []  # once per turn


@pytest.mark.asyncio
async def test_a_long_chat_without_attachments_still_gets_the_over_window_notice(chat_model):
    params = {"model": MODEL, "prompt": "x" * 40_000, "system_prompt": SYSTEM}
    session = SimpleNamespace(session_id="s", metadata={})
    await attachment_context.apply_attachments(session, {}, params)
    (notice,) = params["attachment_notices"]
    assert notice["metadata"]["code"] == "over_window" and session.metadata[attachment_context.OVER_WINDOW_KEY] is True
    quiet = {"model": MODEL, "prompt": "hi", "system_prompt": "sys"}
    await attachment_context.apply_attachments(SimpleNamespace(session_id="s"), {}, quiet)
    assert "attachment_notices" not in quiet


def test_a_zero_prompt_budget_is_reported_not_a_silent_shed(chat_model):
    huge_system = "S" * 22_000  # fits the window with the reply reserve, but leaves no budget for any section
    cwm = get_context_window_manager()
    assert prompt_window.measured_prompt_budget(cwm, MODEL, huge_system) == 0
    assert cwm.estimate_tokens(huge_system) + 2048 <= 8192
    over = prompt_window.send_overflow(MODEL, huge_system, "hi")
    assert over is not None and over["window"] == 8192


def test_the_reply_share_is_clamped_to_its_documented_range(monkeypatch):
    import importlib

    from chat_workflow import limits

    for raw, want in (("0.9", 0.5), ("0.001", 0.05), ("0.25", 0.25)):
        monkeypatch.setenv("AUTOBOT_CHAT_OUTPUT_RESERVE_SHARE", raw)
        assert importlib.reload(limits).OUTPUT_RESERVE_SHARE == want
    monkeypatch.delenv("AUTOBOT_CHAT_OUTPUT_RESERVE_SHARE")
    importlib.reload(limits)


@pytest.mark.asyncio
async def test_the_over_window_notice_is_stored_exactly_once(chat_model, monkeypatch):
    """The send-point notice is stored by persist_notices; the live copy must not be stored again with the turn."""
    from chat_workflow.manager import ChatWorkflowManager

    stored = []

    class _Chat:
        def _build_message_dict(self, sender, content, msg_type, metadata, *_a, **_k):
            return {"sender": sender, "type": msg_type, "metadata": metadata}

        async def add_messages_batch(self, session_id, batch):
            stored.extend(batch)
            return True

    import chat_history

    monkeypatch.setattr(chat_history, "ChatHistoryManager", _Chat)
    (live,) = await attachment_context.send_point_notices(_call("x" * 40_000))
    manager = object.__new__(ChatWorkflowManager)
    stored.extend(manager._build_workflow_message_batch(_Chat(), [live]))  # what _persist_workflow_messages adds
    assert [e["type"] for e in stored] == [attachment_context.NOTICE_TYPE] and stored[0]["sender"] == "system"


@pytest.mark.asyncio
async def test_a_none_context_gives_exactly_one_notice(chat_model, monkeypatch):
    monkeypatch.setattr(attachment_context, "persist_notices", AsyncMock())
    manager = _Manager()
    params = {"model": MODEL, "prompt": "x" * 40_000, "system_prompt": SYSTEM}
    await attachment_context.apply_attachments(manager.session, None, params)
    assert len(params["attachment_notices"]) == 1
    call = _call("x" * 40_000, context=None, manager=manager)  # ctx.context None must not raise a TypeError
    assert await attachment_context.send_point_notices(call) == []


@pytest.mark.asyncio
async def test_a_multi_iteration_turn_with_a_rebuilt_context_notifies_once(chat_model, monkeypatch):
    monkeypatch.setattr(attachment_context, "persist_notices", AsyncMock())
    manager = _Manager()
    seen = []
    for iteration in range(3):  # each iteration gets a fresh (or None) context, as the graph path may build
        call = _call("x" * 40_000, context=None if iteration == 1 else {}, manager=manager)
        seen += await attachment_context.send_point_notices(call)
    assert len(seen) == 1
    manager.session.metadata.clear()  # the next turn starts: said again
    await attachment_context.apply_attachments(
        manager.session, {}, {"model": MODEL, "prompt": "hi", "system_prompt": "s"}
    )
    assert len(await attachment_context.send_point_notices(_call("x" * 40_000, manager=manager))) == 1


@pytest.mark.parametrize(
    "api_kwargs",
    [
        {"thinking": {"type": "enabled", "budget_tokens": 5000}, "temperature": 1},
        {"thinking": {"type": "adaptive"}, "output_config": {"effort": "high"}},
        {"reasoning_effort": "high"},
    ],
)
def test_api_kwargs_never_touch_the_ollama_options_and_the_primary_is_ollama_only(api_kwargs, monkeypatch):
    """The primary request is always the Ollama generate payload, whatever ``configured_provider()`` says."""
    from chat_workflow import llm_provider
    from chat_workflow.manager import ChatWorkflowManager
    from llm_shared.types import ProviderType

    monkeypatch.setattr(llm_provider, "configured_provider", lambda: ProviderType.OPENAI)
    manager = object.__new__(ChatWorkflowManager)
    payload = manager._get_llm_request_payload("any-model:7b", "p", "s", api_kwargs=api_kwargs)
    assert payload["options"]["num_predict"] == 2048 and payload["options"]["num_ctx"] == 8192
    assert payload["stream"] is True and payload["prompt"] == "p" and payload["system"] == "s"
    assert not set(api_kwargs) & {"options", "num_predict", "num_ctx", "prompt", "model", "stream"}


@pytest.mark.asyncio
async def test_a_lost_session_lease_is_not_swallowed_by_the_send_point_check(chat_model, monkeypatch):
    from chat_history.session_lease import SessionLeaseError

    monkeypatch.setattr(attachment_context, "persist_notices", AsyncMock(side_effect=SessionLeaseError("lost")))
    with pytest.raises(SessionLeaseError):
        await attachment_context.send_point_notices(_call("x" * 40_000, context={}))
