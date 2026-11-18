# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The shared 5-field cron validator and every verdict that moved when it replaced two (#18449).

The backend used a hand-written parser; the SLM used croniter unrestricted. Each
parametrized row below is an expression whose verdict changed in at least one of
them, so the PR's list of differences is also its test.
"""

import pytest

from autobot_shared.cron_expression import INVALID_CRON_ERROR_CODE, validate_cron_expression

AGREED_VALID = [
    "* * * * *",
    "*/5 * * * *",
    "0 9 * * 1",
    "0-30 * * * *",
    "0,15,30,45 * * * *",
    "0 0 * * 7",
    "0 0 * * 1-7/2",
]
AGREED_INVALID = ["", "* * * *", "60 * * * *", "a * * * *", "*/0 * * * *", "@daily"]

#: Backend's old parser rejected these; croniter (the engine the schedulers run) accepts them.
NOW_ACCEPTED_BACKEND_WAS_REJECTING = [
    "* * * * MON",  # day-of-week names
    "* * * * 1-MON",
    "* * * JAN *",  # month names
    "* * ? * *",  # '?' placeholder
    "* * L * *",  # last day of month
    "* * * * 1#2",  # nth weekday
    "5-1 * * * *",  # wrapping range
]

#: The backend parser silently clipped out-of-range values; croniter rejects them.
NOW_REJECTED_BACKEND_WAS_CLIPPING = [
    "* * * * 1-31/2",
    "* * * 0,7 *",
    "* * * 0-7 *",
    "* * 0,7 * *",
    "* 1-31/2 * * *",
]

#: The SLM (unrestricted croniter) accepted a 6th "seconds" field or a macro; the contract is 5-field only.
NOW_REJECTED_SLM_WAS_ACCEPTING = ["* * * * * *", "*/5 * * * * *", "0 0 0 * * *"]


@pytest.mark.parametrize("expr", AGREED_VALID)
def test_expressions_both_validators_accepted_still_validate(expr):
    assert validate_cron_expression(expr) is True


@pytest.mark.parametrize("expr", AGREED_INVALID)
def test_expressions_both_validators_rejected_still_fail(expr):
    assert validate_cron_expression(expr) is False


@pytest.mark.parametrize("expr", NOW_ACCEPTED_BACKEND_WAS_REJECTING)
def test_backend_difference_now_accepted(expr):
    assert validate_cron_expression(expr) is True


@pytest.mark.parametrize("expr", NOW_REJECTED_BACKEND_WAS_CLIPPING)
def test_backend_difference_now_rejected(expr):
    assert validate_cron_expression(expr) is False


@pytest.mark.parametrize("expr", NOW_REJECTED_SLM_WAS_ACCEPTING)
def test_slm_difference_six_fields_now_rejected(expr):
    assert validate_cron_expression(expr) is False


def test_non_string_is_invalid_and_the_error_code_is_the_contract_one():
    assert validate_cron_expression(None) is False  # type: ignore[arg-type]
    assert INVALID_CRON_ERROR_CODE == "schedule.invalid_cron"
