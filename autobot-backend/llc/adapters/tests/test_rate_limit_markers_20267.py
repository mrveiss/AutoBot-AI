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


def _expired_login_tail(message_uuid: str) -> str:
    """The shape of a real expired-login transcript tail (assistant event + result event)."""
    assistant = {
        "type": "assistant",
        "uuid": message_uuid,
        "error": "authentication_failed",
        "is_api_error_message": True,
    }
    result = {
        "type": "result",
        "subtype": "success",
        "is_error": True,
        "api_error_status": None,
        "total_cost_usd": 0,
        "result": _AUTH_MESSAGE,
    }
    return "\n".join(json.dumps(o) for o in (assistant, result)) + "\n"


def test_real_failure_tail_with_529_in_a_uuid_is_not_rate_limited() -> None:
    tail = _expired_login_tail("529eb50f-36a7-4f6c-b7ad-86c863838700")
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
