# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A claude_code run whose result line says it failed is FAILED, not COMPLETED (#20202).

The CLI writes ``subtype="success"`` next to ``is_error=true`` on an API error, so
the lines below reproduce the shape of a real expired-login transcript.
"""

import json
import logging
import time
from unittest.mock import AsyncMock, patch

import pytest

from llc.adapters.claude_code_adapter import (
    AUTH_FAILED_REASON,
    ERROR_RESULT_REASON,
    ClaudeCodeAdapter,
    _output_path,
    _state_path,
)
from llc.models.enums import LLCRunStatus

_AUTH_TEXT = "Failed to authenticate: OAuth session expired and could not be refreshed"
_ASSISTANT_AUTH = {
    "type": "assistant",
    "message": {"role": "assistant", "content": [{"type": "text", "text": _AUTH_TEXT}]},
    "error": "authentication_failed",
    "is_api_error_message": True,
}
_RESULT_AUTH = {
    "type": "result",
    "subtype": "success",
    "is_error": True,
    "num_turns": 1,
    "api_error_status": None,
    "terminal_reason": "api_error",
    "result": _AUTH_TEXT,
}


async def _final_status(tmp_path, events: list[dict]):
    run_id = "4001/session-20202"
    output_file = _output_path(str(tmp_path), "agent-auth", run_id)
    with open(output_file, "w", encoding="utf-8") as fh:
        fh.write("".join(json.dumps(e) + "\n" for e in events))
    state = {
        "pid": 4001,
        "session_id": "session-20202",
        "agent_id": "agent-auth",
        "output_file": output_file,
        "started_at": time.time(),
        "timeout_seconds": 3600,
    }
    with open(_state_path(str(tmp_path), run_id), "w", encoding="utf-8") as fh:
        json.dump(state, fh)
    cfg = {"agent_id": "agent-auth", "adapter_config": {"output_dir": str(tmp_path)}}
    with (
        patch("os.kill", side_effect=ProcessLookupError()),
        patch("llc.adapters.claude_code_adapter.get_async_redis_client", new_callable=AsyncMock, return_value=None),
    ):
        return await ClaudeCodeAdapter().status(cfg, run_id)


@pytest.mark.asyncio
async def test_expired_login_result_line_is_failed_with_auth_reason(tmp_path, caplog) -> None:
    with caplog.at_level(logging.ERROR):
        result = await _final_status(tmp_path, [_ASSISTANT_AUTH, _RESULT_AUTH])

    assert result.status == LLCRunStatus.FAILED
    assert result.error == AUTH_FAILED_REASON
    assert _AUTH_TEXT not in (result.error or "")
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert errors and AUTH_FAILED_REASON in errors[-1].getMessage()
    assert _AUTH_TEXT not in errors[-1].getMessage()


@pytest.mark.asyncio
async def test_auth_failure_is_recognised_by_status_code_field(tmp_path) -> None:
    result_401 = dict(_RESULT_AUTH, api_error_status=401, result="x")
    result = await _final_status(tmp_path, [result_401])
    assert (result.status, result.error) == (LLCRunStatus.FAILED, AUTH_FAILED_REASON)


@pytest.mark.asyncio
async def test_is_error_with_success_subtype_is_failed_not_completed(tmp_path) -> None:
    other = dict(_RESULT_AUTH, result="upstream exploded")
    result = await _final_status(tmp_path, [other])
    assert (result.status, result.error) == (LLCRunStatus.FAILED, ERROR_RESULT_REASON)


@pytest.mark.asyncio
async def test_non_success_subtype_is_failed(tmp_path) -> None:
    result = await _final_status(
        tmp_path, [{"type": "result", "subtype": "error_max_turns", "is_error": False, "num_turns": 9}]
    )
    assert (result.status, result.error) == (LLCRunStatus.FAILED, ERROR_RESULT_REASON)


@pytest.mark.asyncio
async def test_clean_success_stays_completed(tmp_path) -> None:
    ok = {"type": "result", "subtype": "success", "is_error": False, "num_turns": 3, "result": "done"}
    result = await _final_status(tmp_path, [ok])
    assert result.status == LLCRunStatus.COMPLETED
    assert result.error is None
