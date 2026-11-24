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
    (notice,) = attachment_context._window_notice(big)
    assert notice["metadata"]["code"] == "over_window" and notice["metadata"]["window"] == 8192
    assert attachment_context._window_notice({"model": MODEL, "prompt": "hi", "system_prompt": "sys"}) == []


def test_send_point_warns_when_the_prompt_is_over_the_window(chat_model, caplog):
    with caplog.at_level(logging.WARNING):
        assert prompt_window.warn_if_over_window(MODEL, SYSTEM, "x" * 40_000) is True
    assert "input will be cut" in caplog.text
    assert prompt_window.warn_if_over_window(MODEL, "sys", "hi") is False


def test_prompt_eval_count_at_the_window_is_logged(chat_model, caplog):
    with caplog.at_level(logging.WARNING):
        assert prompt_window.note_prompt_eval({"done": True, "prompt_eval_count": 8192}, MODEL) is True
    assert "reached the window" in caplog.text
    assert prompt_window.note_prompt_eval({"done": True, "prompt_eval_count": 900}, MODEL) is False
    assert prompt_window.note_prompt_eval({"done": False, "prompt_eval_count": 8192}, MODEL) is False


def test_a_model_that_is_not_the_chat_model_keeps_its_declared_window():
    cwm = get_context_window_manager()
    assert prompt_window.request_window_tokens(cwm, "some-other-model") == cwm.get_adaptive_context_length(
        "some-other-model"
    )


def test_a_cloud_provider_never_gets_the_ollama_num_ctx(chat_model, monkeypatch):
    from llm_shared.types import ProviderType

    cwm = get_context_window_manager()
    monkeypatch.setattr(prompt_window, "configured_provider", lambda: ProviderType.OPENAI)
    assert prompt_window.request_window_tokens(cwm, MODEL) == cwm.get_adaptive_context_length(MODEL)
    assert prompt_window.note_prompt_eval({"done": True, "prompt_eval_count": 8192}, MODEL) is False


def test_the_reply_share_is_clamped_to_its_documented_range(monkeypatch):
    import importlib

    from chat_workflow import limits

    for raw, want in (("0.9", 0.5), ("0.001", 0.05), ("0.25", 0.25)):
        monkeypatch.setenv("AUTOBOT_CHAT_OUTPUT_RESERVE_SHARE", raw)
        assert importlib.reload(limits).OUTPUT_RESERVE_SHARE == want
    monkeypatch.delenv("AUTOBOT_CHAT_OUTPUT_RESERVE_SHARE")
    importlib.reload(limits)
