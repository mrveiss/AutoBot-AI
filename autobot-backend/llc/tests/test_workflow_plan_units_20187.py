# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Workflow plan follow-ups that need no database: policy targets, handoff and edge case treatments (#20168, #20187)."""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from llc.services.company_os import plan_breakdown
from llc.services.company_os.errors import GraphInvalid
from llc.services.company_os.plan_convert_build import _edge_case_kind, _handoff_kind
from llc.services.company_os.plan_types import EdgeCaseTreatmentKind as E
from llc.services.company_os.plan_types import HandoffTreatmentKind as H
from llc.services.company_os.plan_types import Label, SubStepState


def _plan(*subs):
    return NS(sub_steps=list(subs), approval_policies=[])


def _sub(key, state=SubStepState.PROPOSED, label=Label.AI):
    return NS(key=key, state=state, classification=label)


def _policy(key, *subs):
    return NS(key=key, sub_step_keys=list(subs))


def test_a_policy_on_a_current_or_by_hand_sub_step_is_refused():
    plan = _plan(_sub("ai"), _sub("cur", SubStepState.CURRENT, None), _sub("hand", label=Label.BY_HAND))
    for target, word in (("cur", "current"), ("hand", "By Hand")):
        with pytest.raises(GraphInvalid) as exc:
            plan_breakdown.replace_policies(plan, [_policy("g", target)])
        assert word in str(exc.value.args[0])
    assert plan.approval_policies == []


def test_a_policy_on_an_ai_sub_step_is_kept_and_duplicates_are_still_named():
    plan = _plan(_sub("a"), _sub("b"))
    plan_breakdown.replace_policies(plan, [_policy("g", "a")])
    assert [p.key for p in plan.approval_policies] == ["g"]
    with pytest.raises(GraphInvalid) as exc:
        plan_breakdown.replace_policies(plan, [_policy("g", "a", "b"), _policy("g", "a")])
    assert str(exc.value.args[0]) == "duplicate approval policy key 'g'; sub-step 'a' is covered by two policies"


def test_repeated_names_each_repeat_once_in_order():
    assert plan_breakdown._repeated(["b", "a", "b", "a", "b", "c"]) == ["a", "b"]


_CASE = NS(key="e", classification=Label.BY_HAND, sub_step_key="lead")


def test_a_by_hand_edge_case_is_handled_in_step_only_when_the_step_is_a_node():
    assert _edge_case_kind(_CASE, set(), {"lead", "other"}) is E.HANDLED_IN_STEP
    assert _edge_case_kind(_CASE, set(), {"other"}) is E.DOCUMENTATION  # a leading By Hand step is handbook text
    assert _edge_case_kind(NS(**{**_CASE.__dict__, "sub_step_key": None}), set(), {"lead"}) is E.DOCUMENTATION
    assert _edge_case_kind(_CASE, {"e"}, {"other"}) is E.BRANCH


def _handoff(frm, to, from_step="s1", to_step="s2"):
    return NS(key="h", from_lane=frm, to_lane=to, from_step=from_step, to_step=to_step)


def test_a_handoff_transition_is_claimed_only_between_neighbouring_lanes():
    adjacent, owning = {("a", "b"), ("b", "c")}, {"a", "b", "c"}
    assert _handoff_kind(_handoff("a", "b"), "s2", adjacent, owning, {}) is H.HANDOFF_TRANSITION
    assert _handoff_kind(_handoff("a", "c"), "s2", adjacent, owning, {}) is H.OUT_OF_SCOPE  # nothing drafted
    assert _handoff_kind(_handoff("c", "a"), "s2", adjacent, owning, {}) is H.OUT_OF_SCOPE  # against the chain
    assert _handoff_kind(_handoff("x", "a"), "s2", adjacent, owning, {}) is H.TRIGGER
    assert _handoff_kind(_handoff("a", "b"), "s9", adjacent, owning, {}) is H.OUT_OF_SCOPE
