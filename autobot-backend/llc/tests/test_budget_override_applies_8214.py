# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A budget override is compared against the current limit, and its decision wakes the agent it names (#8214)."""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from llc.models.enums import ApprovalType
from llc.services.approval_hooks import ApprovalHookError, BudgetOverridePayload, _check_override_applies
from llc.services.wake_events import _decided_wake_ref


def _row(mode="dollars", limit="10", tokens=None):  # noqa: ANN001, ANN202
    return SimpleNamespace(budget_mode=mode, budget_limit=Decimal(limit), token_limit=tokens)


def _ask(**fields):  # noqa: ANN003, ANN202
    return BudgetOverridePayload(agent_id="agent-a", **fields)


def test_a_stale_raise_naming_the_same_mode_cannot_lower_the_limit() -> None:
    with pytest.raises(ApprovalHookError, match="must raise"):
        _check_override_applies(_row(limit="10"), _ask(budget_mode="dollars", budget_limit=Decimal("8")))


def test_a_mode_only_override_repeating_the_mode_is_refused() -> None:
    with pytest.raises(ApprovalHookError, match="must change"):
        _check_override_applies(_row(), _ask(budget_mode="dollars"))


def test_a_real_mode_switch_stays_allowed() -> None:
    _check_override_applies(_row(mode="tokens", tokens=100), _ask(budget_mode="dollars", budget_limit=Decimal("1")))
    _check_override_applies(_row(), _ask(budget_mode="tokens"))


def test_a_raise_naming_the_same_mode_applies() -> None:
    _check_override_applies(_row(limit="10"), _ask(budget_mode="dollars", budget_limit=Decimal("12")))


def test_a_budget_override_wakes_the_agent_it_names_not_the_person_who_asked() -> None:
    approval = SimpleNamespace(
        approval_type=ApprovalType.BUDGET_OVERRIDE.value, context={"agent_id": "agent-a"}, requested_by_agent="a-person"
    )
    assert _decided_wake_ref(approval) == "agent-a"


def test_other_approvals_wake_their_requester() -> None:
    approval = SimpleNamespace(
        approval_type=ApprovalType.HIRE.value, context={"agent_id": "new"}, requested_by_agent="ceo"
    )
    assert _decided_wake_ref(approval) == "ceo"
