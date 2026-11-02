# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The adapter reports how a run was billed, from the stream's init event (#20266)."""

import json
import time
from unittest.mock import AsyncMock, patch

import pytest

from llc.adapters.base import BILLING_API, BILLING_SUBSCRIPTION
from llc.adapters.claude_code_adapter import ClaudeCodeAdapter, _output_path, _state_path
from llc.adapters.claude_code_subscription_adapter import ClaudeCodeSubscriptionAdapter
from llc.models.enums import LLCRunStatus


def _init(source) -> dict:
    event = {"type": "system", "subtype": "init", "session_id": "s", "model": "claude-sonnet-4-6", "tools": ["Bash"]}
    if source is not None:
        event["apiKeySource"] = source
    return event


_SUCCESS = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "num_turns": 3,
    "result": "done",
    "total_cost_usd": 0.42,
    "usage": {"input_tokens": 10, "cache_read_input_tokens": 90, "output_tokens": 5},
}
_TURN_LIMIT = dict(_SUCCESS, subtype="error_max_turns", is_error=False)


async def _status(tmp_path, events: list[dict], adapter):
    run_id = "4002/session-20266"
    output_file = _output_path(str(tmp_path), "agent-bill", run_id)
    with open(output_file, "w", encoding="utf-8") as fh:
        fh.write("".join(json.dumps(e) + "\n" for e in events))
    state = {"pid": 4002, "session_id": "s", "agent_id": "agent-bill", "output_file": output_file}
    state.update(started_at=time.time(), timeout_seconds=3600)
    with open(_state_path(str(tmp_path), run_id), "w", encoding="utf-8") as fh:
        json.dump(state, fh)
    cfg = {"agent_id": "agent-bill", "adapter_config": {"output_dir": str(tmp_path)}}
    with (
        patch("os.kill", side_effect=ProcessLookupError()),
        patch("llc.adapters.claude_code_adapter.get_async_redis_client", new_callable=AsyncMock, return_value=None),
    ):
        return await adapter.status(cfg, run_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter_cls", [ClaudeCodeAdapter, ClaudeCodeSubscriptionAdapter])
async def test_login_without_api_key_reports_subscription(tmp_path, adapter_cls) -> None:
    result = await _status(tmp_path, [_init("none"), _SUCCESS], adapter_cls())
    assert (result.status, result.billing) == (LLCRunStatus.COMPLETED, BILLING_SUBSCRIPTION)
    assert (result.tokens_in, result.tokens_out) == (100, 5)


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["ANTHROPIC_API_KEY", "apiKeyHelper", "/login managed key"])
async def test_api_key_reports_api(tmp_path, source) -> None:
    result = await _status(tmp_path, [_init(source), _SUCCESS], ClaudeCodeAdapter())
    assert result.billing == BILLING_API


@pytest.mark.asyncio
@pytest.mark.parametrize("events", [[_SUCCESS], [_init(None), _SUCCESS], [_init(7), _SUCCESS]])
async def test_unknown_billing_stays_none(tmp_path, events) -> None:
    result = await _status(tmp_path, events, ClaudeCodeAdapter())
    assert result.status == LLCRunStatus.COMPLETED and result.billing is None


@pytest.mark.asyncio
async def test_turn_limit_run_is_failed_with_billing_and_tokens(tmp_path) -> None:
    result = await _status(tmp_path, [_init("none"), _TURN_LIMIT], ClaudeCodeAdapter())
    assert result.status == LLCRunStatus.FAILED
    assert (result.billing, result.tokens_in, result.tokens_out) == (BILLING_SUBSCRIPTION, 100, 5)
