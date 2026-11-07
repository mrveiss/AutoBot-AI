# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Rolling summary of older chat turns (#20852)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat_history import rolling_summary as rs
from chat_history.context_overflow import ConversationSummarizer, SummarizationFailed
from chat_workflow.llm_handler import LLMHandlerMixin

CONSTRAINT = "CONSTRAINT: never use sudo on the build host"


class StubSummarizer:
    """Deterministic: keeps every line marked CONSTRAINT, from the prior summary and new turns."""

    def __init__(self):
        self.calls = []

    async def summarize_messages(self, messages, model_name, prior_summary="", max_tokens=500):
        self.calls.append({"n": len(messages), "prior": prior_summary, "model": model_name})
        kept = [prior_summary] if prior_summary else []
        kept += [m["content"] for m in messages if "CONSTRAINT" in m["content"]]
        return "\n".join(kept) or "no constraints"


def _history(n, constraint_turn=1):
    return [
        {"user": CONSTRAINT if i == constraint_turn else f"question {i}", "assistant": f"answer {i}"}
        for i in range(1, n + 1)
    ]


def _context(history, summary):
    session = SimpleNamespace(conversation_history=history)
    return LLMHandlerMixin.__new__(LLMHandlerMixin)._build_conversation_context(session, summary)


@pytest.mark.asyncio
async def test_nothing_older_than_recent_turns_means_no_summary():
    stub = StubSummarizer()
    assert await rs.fold_older_turns({}, _history(2), "m", stub) == ""
    assert stub.calls == []


@pytest.mark.asyncio
async def test_constraint_from_turn_1_present_at_turn_10():
    meta, stub = {}, StubSummarizer()
    history = _history(10)
    summary = ""
    for turn in range(1, 11):  # a prompt is built every turn, folding incrementally
        summary = await rs.fold_older_turns(meta, history[:turn], "m", stub)
    context = _context(history, summary)
    assert CONSTRAINT in context
    assert "question 9" in context and "question 10" in context  # last 2 verbatim
    assert "question 5" not in context  # not replayed verbatim


@pytest.mark.asyncio
async def test_fold_is_incremental_and_cached():
    meta, stub = {}, StubSummarizer()
    history = _history(6)
    await rs.fold_older_turns(meta, history, "m", stub)  # folds turns 1-4
    assert stub.calls[-1]["n"] == 8 and stub.calls[-1]["prior"] == ""
    await rs.fold_older_turns(meta, history, "m", stub)  # unchanged: cache hit
    assert len(stub.calls) == 1
    await rs.fold_older_turns(meta, history + _history(1), "m", stub)  # one more turn older
    assert len(stub.calls) == 2
    assert stub.calls[-1]["n"] == 2 and CONSTRAINT in stub.calls[-1]["prior"]


@pytest.mark.asyncio
async def test_expired_cache_is_rebuilt_from_the_turns():
    meta, stub = {}, StubSummarizer()
    history = _history(6)
    await rs.fold_older_turns(meta, history, "m", stub, now=1000.0)
    await rs.fold_older_turns(meta, history, "m", stub, now=1000.0 + rs.ROLLING_SUMMARY_TTL_SECONDS + 1)
    assert len(stub.calls) == 2 and stub.calls[-1]["prior"] == "" and stub.calls[-1]["n"] == 8


@pytest.mark.asyncio
async def test_incomplete_turn_is_not_summarised():
    stub = StubSummarizer()
    history = _history(5) + [{"user": "in flight", "assistant": ""}]
    await rs.fold_older_turns({}, history, "m", stub)
    assert stub.calls[-1]["n"] == 6  # turns 1-3 only


@pytest.mark.asyncio
async def test_failure_falls_back_to_dropping_with_a_warning_and_backs_off(caplog):
    meta = {}
    failing = SimpleNamespace(summarize_messages=AsyncMock(side_effect=SummarizationFailed("down")))
    with caplog.at_level("WARNING", logger=rs.logger.name):
        assert await rs.fold_older_turns(meta, _history(6), "m", failing, now=10.0) == ""
    assert any("Rolling summary failed" in r.getMessage() for r in caplog.records)
    # within the backoff window the failing summariser is not called again
    assert await rs.fold_older_turns(meta, _history(6), "m", failing, now=11.0) == ""
    assert failing.summarize_messages.await_count == 1
    # the turn itself still builds: recent turns only, no summary section
    context = _context(_history(6), "")
    assert "Summary of earlier" not in context and "question 6" in context


def test_context_without_summary_is_the_old_recent_only_shape():
    context = _context(_history(6), "")
    assert context.startswith("\n**Recent Context:**\n") and "question 3" not in context


@pytest.mark.asyncio
async def test_real_summarizer_prompt_instructs_keeping_constraints_and_decisions():
    gateway = MagicMock()
    gateway.chat = AsyncMock(return_value=SimpleNamespace(content="ok", error=None))
    summarizer = ConversationSummarizer()
    with patch.object(summarizer, "_get_gateway", AsyncMock(return_value=gateway)):
        await summarizer.summarize_messages(
            [{"role": "user", "content": CONSTRAINT}], "local-model", prior_summary="PRIOR-S", max_tokens=123
        )
    kwargs = gateway.chat.await_args.kwargs
    prompt = kwargs["messages"][0]["content"]
    assert "constraint" in prompt and "decision" in prompt and "never drop one" in prompt
    assert "carry forward every constraint and decision" in prompt
    assert "PRIOR-S" in prompt and CONSTRAINT in prompt
    assert kwargs["model_name"] == "local-model" and kwargs["max_tokens"] == 123


@pytest.mark.asyncio
async def test_hook_endpoint_and_rolling_fold_call_the_same_summariser():
    from chat_workflow import compact_hook

    sentinel = AsyncMock(return_value="SUMMARY")
    with patch.object(ConversationSummarizer, "summarize_messages", sentinel):
        await rs.fold_older_turns({}, _history(6), "m")
        assert sentinel.await_count == 1  # rolling fold

        long_msgs = [{"role": "user", "content": "x" * 2000} for _ in range(60)]
        task = MagicMock()
        with patch.object(compact_hook, "compact_snapshot_task", task, create=True):
            await compact_hook.on_pre_compact("s", long_msgs, None, "llama3")
        assert sentinel.await_count == 2  # compact hook
        assert "SUMMARY" in task.delay.call_args.args[1]

        # control: below the threshold the hook does not summarise
        await compact_hook.on_pre_compact("s", long_msgs[:2], None, "llama3")
        assert sentinel.await_count == 2


@pytest.mark.asyncio
async def test_summarize_endpoint_uses_the_shared_summariser():
    from api import chat as chat_api

    sentinel = AsyncMock(return_value="ENDPOINT-SUMMARY")
    history = MagicMock()
    history.get_messages = AsyncMock(return_value=[{"message_id": "a", "role": "user", "content": "hi"}])
    body = SimpleNamespace(session_id="s", message_ids=["a"], target_length=77)
    cfg = MagicMock()
    cfg.get_selected_model.return_value = "local-model"
    with (
        patch.object(ConversationSummarizer, "summarize_messages", sentinel),
        patch.object(chat_api, "validate_chat_ownership", AsyncMock()),
        patch.object(chat_api, "get_chat_history_manager", return_value=history),
        patch.object(chat_api, "provide_config_manager", return_value=cfg),
    ):
        fn = getattr(chat_api.summarize_conversation, "__wrapped__", chat_api.summarize_conversation)
        resp = await fn(body, MagicMock(), {"user_id": "u"})
    assert resp.data["summary"] == "ENDPOINT-SUMMARY"
    assert sentinel.await_args.args[1] == "local-model" and sentinel.await_args.kwargs["max_tokens"] == 77
