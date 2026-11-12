# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A checkout request whose agent id cannot be fenced is a validation error, not a 404 (#21083).

``fence_agent`` splits the fence value on the generation separator, so an agent id carrying one is
refused. The route used to let the service's ValueError reach its generic ``except ValueError``
handler, which answered 404 "Internal server error".
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from llc.api.work_items import CheckoutRequest
from llc.services import work_item_own_task as own_task


@pytest.mark.parametrize("agent_id", ["agent#1", "#", f"{uuid.uuid4()}#gen-1"])
def test_a_checkout_request_refuses_an_agent_id_carrying_the_separator(agent_id: str) -> None:
    with pytest.raises(ValidationError, match="must not contain"):
        CheckoutRequest(agent_id=agent_id, run_id="run-1")


def test_a_checkout_request_refuses_the_separator_with_no_run_id() -> None:
    with pytest.raises(ValidationError, match="must not contain"):
        CheckoutRequest(agent_id="agent#1")


def test_a_checkout_request_keeps_a_plain_agent_id() -> None:
    agent_id = str(uuid.uuid4())
    assert CheckoutRequest(agent_id=agent_id, run_id="run-1").agent_id == agent_id


def test_the_fence_value_still_refuses_the_separator_for_callers_that_skip_the_request_model() -> None:
    """``checkout_next`` and other service callers reach ``checkout_fence_value`` without a request model."""
    with pytest.raises(ValueError, match="must not contain"):
        own_task.checkout_fence_value("agent#1", "run-1")
