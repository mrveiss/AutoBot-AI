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


def _call(prompt, context=None, system=SYSTEM):
    ctx = SimpleNamespace(
        selected_model=MODEL, system_prompt=system, session_id="s", context={} if context is None else context
    )
    return SimpleNamespace(ctx=ctx, prompt=prompt)


@pytest.mark.asyncio
async def test_send_point_notices_once_per_turn_when_the_prompt_is_over_the_window(chat_model, caplog, monkeypatch):
    monkeypatch.setattr(attachment_context, "persist_notices", AsyncMock())
    call = _call("x" * 40_000)
    with caplog.at_level(logging.WARNING):
        (notice,) = await attachment_context.send_point_notices(call)
    assert "input will be cut" in caplog.text and notice.metadata["code"] == "over_window"
    assert await attachment_context.send_point_notices(call) == []  # the next iteration of the turn stays quiet
    assert await attachment_context.send_point_notices(_call("hi", system="sys")) == []


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


def test_a_hop_over_its_window_is_logged(caplog, monkeypatch):
    cwm = get_context_window_manager()
    monkeypatch.setattr(cwm, "get_adaptive_context_length", lambda m=None: 1000)
    with caplog.at_level(logging.WARNING):
        assert prompt_window.warn_if_hop_over_window("hop-model", "s", "x" * 40_000) is True
    assert "Failover hop" in caplog.text


@pytest.mark.asyncio
async def test_a_long_chat_without_attachments_still_gets_the_over_window_notice(chat_model):
    params = {"model": MODEL, "prompt": "x" * 40_000, "system_prompt": SYSTEM}
    context = {}
    await attachment_context.apply_attachments(SimpleNamespace(session_id="s"), context, params)
    (notice,) = params["attachment_notices"]
    assert notice["metadata"]["code"] == "over_window" and context[attachment_context.OVER_WINDOW_KEY] is True
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
