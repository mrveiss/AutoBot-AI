# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``is_rate_limit_output`` must not match digits inside ids, costs or counts (#20267).

Observed 2026-10-31: the failed-run tail of an expired-login run carried the message
uuid ``529eb50f-...``; the bare ``529`` keyword read it as a provider rate limit.
"""

import json

import pytest

from llc.adapters.claude_result_failure import is_auth_failure_output
from llc.adapters.subprocess_support import final_result_event, is_rate_limit_output

_AUTH_MESSAGE = "Failed to authenticate: OAuth session expired and could not be refreshed"
# The uuid of the expired-login run whose "529" was read as a provider rate limit.
_REAL_UUID = "529eb50f-36a7-4f6c-b7ad-86c863838700"


def _expired_login_tail(message_uuid: str) -> str:
    """The exact event shape of the real expired-login transcript (session content stripped).

    Real fields: the assistant event is the CLI's synthetic API-error message
    (``error``/``is_api_error_message``) with the fixed error line as its only text; the
    result event is ``is_error`` with ``subtype`` ``success`` and ``terminal_reason`` ``api_error``.
    """
    assistant = {
        "type": "assistant",
        "message": {
            "model": "<synthetic>",
            "role": "assistant",
            "stop_reason": "stop_sequence",
            "content": [{"type": "text", "text": _AUTH_MESSAGE}],
        },
        "parent_tool_use_id": None,
        "session_id": "00000000-0000-0000-0000-000000000000",
        "uuid": message_uuid,
        "timestamp": "2026-10-31T11:30:12.841Z",
        "error": "authentication_failed",
        "is_api_error_message": True,
    }
    result = {
        "type": "result",
        "subtype": "success",
        "is_error": True,
        "api_error_status": None,
        "terminal_reason": "api_error",
        "duration_api_ms": 0,
        "total_cost_usd": 0,
        "num_turns": 1,
        "result": _AUTH_MESSAGE,
        "session_id": "00000000-0000-0000-0000-000000000000",
        "uuid": "1afaedfc-4884-49ee-b43e-f530f57d6626",
    }
    return "\n".join(json.dumps(o) for o in (assistant, result)) + "\n"


def test_real_failure_tail_with_529_in_a_uuid_is_not_rate_limited() -> None:
    tail = _expired_login_tail(_REAL_UUID)
    assert "529" in tail
    assert not is_rate_limit_output(tail)
    assert is_auth_failure_output(tail, final_result_event(tail))


@pytest.mark.parametrize(
    "text",
    [
        '{"uuid": "1c36f41a-4298-463d-a7cf-61f9dc19", "session_id": "x"}',
        '{"total_cost_usd": 0.0429, "num_turns": 429}',
        '{"duration_ms": 5290, "id": "msg_4290"}',
        "processed 429 files, cost $5.29",
        "session 3a4297b1-0000-0000-0000-000000000529",
    ],
)
def test_digits_inside_ids_costs_and_counts_do_not_match(text: str) -> None:
    assert not is_rate_limit_output(text)


@pytest.mark.parametrize(
    "text",
    [
        '{"type": "result", "is_error": true, "api_error_status": 429}',
        '{"api_error_status":529,"result":"x"}',
        '{"type": "error", "error": {"status": 429}}',
        "HTTP 529 returned by API",
        "Error code: 429 - too fast",
        "API Error: 429",
        "status_code=429",
    ],
)
def test_true_429_and_529_still_match(text: str) -> None:
    assert is_rate_limit_output(text)


@pytest.mark.parametrize(
    "text",
    ["rate_limit_error", "You hit the rate limit", "Too Many Requests", "API is overloaded", "Monthly quota exceeded"],
)
def test_phrase_markers_still_match(text: str) -> None:
    assert is_rate_limit_output(text)


def test_rate_limit_event_on_a_successful_run_is_not_a_marker() -> None:
    event = {
        "type": "rate_limit_event",
        "rate_limit_info": {"status": "allowed", "rateLimitType": "five_hour", "overageStatus": "rejected"},
    }
    assert not is_rate_limit_output(json.dumps(event))


def _jsonl(*events: dict) -> str:
    return "\n".join(json.dumps(e) for e in events) + "\n"


_TOOL_OUTPUT = {
    "type": "user",
    "message": {"content": [{"type": "tool_result", "content": "billing quota exhausted; server overloaded"}]},
}
_ASSISTANT_TEXT = {
    "type": "assistant",
    "message": {"content": [{"type": "text", "text": "The quota check says the API is overloaded, too many requests"}]},
}


def test_tool_output_and_assistant_text_with_the_words_do_not_match() -> None:
    assert not is_rate_limit_output(_jsonl(_TOOL_OUTPUT, _ASSISTANT_TEXT))


def test_failed_result_with_unrelated_error_after_such_text_is_not_rate_limited() -> None:
    result = {"type": "result", "is_error": True, "result": "upstream exploded"}
    assert not is_rate_limit_output(_jsonl(_TOOL_OUTPUT, _ASSISTANT_TEXT, result))


@pytest.mark.parametrize(
    "event",
    [
        {"type": "result", "is_error": True, "result": "API Error: Overloaded"},
        {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}},
        {"type": "error", "error": {"type": "rate_limit_error", "message": "x"}},
        {"type": "assistant", "error": "rate_limit", "is_api_error_message": True, "message": {"content": []}},
        {"type": "result", "is_error": True, "api_error_status": 529, "result": ""},
        {"type": "error", "message": "quota exceeded for this session"},
    ],
)
def test_structured_error_events_match(event: dict) -> None:
    assert is_rate_limit_output(_jsonl(_TOOL_OUTPUT, event))


@pytest.mark.parametrize(
    "text",
    ["Error: API is overloaded, please retry later", "Monthly quota exceeded for this account", "overloaded_error"],
)
def test_error_shaped_plain_text_matches(text: str) -> None:
    assert is_rate_limit_output(text)


@pytest.mark.parametrize("text", ["the quota file is in /etc/quota", "overloaded operator in C++", "quota: 5 GB"])
def test_plain_text_mentioning_the_words_without_an_error_does_not_match(text: str) -> None:
    assert not is_rate_limit_output(text)


def _status_run(tmp_path, events):
    from llc.adapters.tests.test_claude_code_auth_failure_20202 import _final_status

    return _final_status(tmp_path, events)


@pytest.mark.asyncio
async def test_failed_run_whose_tool_output_says_quota_stays_failed(tmp_path) -> None:
    from llc.models.enums import LLCRunStatus

    result_event = {"type": "result", "subtype": "success", "is_error": True, "result": "upstream exploded"}
    result = await _status_run(tmp_path, [_TOOL_OUTPUT, _ASSISTANT_TEXT, result_event])
    assert result.status == LLCRunStatus.FAILED


@pytest.mark.asyncio
async def test_real_overloaded_error_run_is_rate_limited(tmp_path) -> None:
    from llc.models.enums import LLCRunStatus

    result_event = {"type": "result", "subtype": "success", "is_error": True, "result": "API Error: Overloaded"}
    result = await _status_run(tmp_path, [_TOOL_OUTPUT, result_event])
    assert result.status == LLCRunStatus.RATE_LIMITED


@pytest.mark.asyncio
async def test_expired_login_run_with_529_uuid_is_auth_failed_not_rate_limited(tmp_path) -> None:
    from llc.models.enums import LLCRunStatus

    events = [json.loads(line) for line in _expired_login_tail(_REAL_UUID).splitlines()]
    result = await _status_run(tmp_path, events)
    assert result.status == LLCRunStatus.FAILED
