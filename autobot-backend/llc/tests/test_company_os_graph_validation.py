# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Pure validation of a Company OS workflow graph (#18390). No database."""

import uuid

from llc.services.company_os.graph_types import GraphContext, GraphSpec, HandoffTarget
from llc.services.company_os.graph_validation import validate_graph

ROLE_A, ROLE_B = uuid.uuid4(), uuid.uuid4()


def _spec(nodes, transitions) -> GraphSpec:
    return GraphSpec.model_validate({"nodes": nodes, "transitions": transitions})


def _ctx(**kw) -> GraphContext:
    base = dict(
        own_workflow_id="wf",
        own_role_id=ROLE_A,
        processes={"p1": ["sql"], "p2": []},
        meta_skills=frozenset({"meta1"}),
        handoff_targets={"other": HandoffTarget("workflow", ROLE_B), "mine": HandoffTarget("workflow", ROLE_A)},
        held_skills=frozenset({"sql"}),
    )
    base.update(kw)
    return GraphContext(**base)


START = {"key": "s", "kind": "start"}
END_OK = {"key": "ok", "kind": "end", "end_outcome": "done"}
END_BAD = {"key": "bad", "kind": "end", "end_outcome": "failed"}
P1 = {"key": "a", "kind": "process", "process_key": "p1"}


def _good():
    return _spec(
        [START, P1, END_OK, END_BAD],
        [
            {"from_node": "s", "kind": "success", "to_node": "a"},
            {"from_node": "a", "kind": "success", "to_node": "ok"},
            {"from_node": "a", "kind": "failure", "to_node": "bad", "retry_max": 2},
            {"from_node": "ok", "kind": "handoff", "handoff_workflow_id": "other"},
        ],
    )


def test_well_formed_graph_has_no_errors_or_warnings():
    report = validate_graph(_good(), _ctx())
    assert report.errors == [] and report.warnings == []


def test_exactly_one_start_and_at_least_one_end():
    assert any("exactly one Start" in e for e in validate_graph(_spec([END_OK], []), _ctx()).errors)
    two = _spec([START, {"key": "s2", "kind": "start"}, END_OK], [])
    assert any("found 2" in e for e in validate_graph(two, _ctx()).errors)
    assert any("at least one End" in e for e in validate_graph(_spec([START], []), _ctx()).errors)


def test_unreachable_end_and_node_are_errors():
    spec = _spec([START, END_OK, END_BAD, P1], [{"from_node": "s", "kind": "success", "to_node": "ok"}])
    errors = validate_graph(spec, _ctx()).errors
    assert any("End 'bad' is not reachable" in e for e in errors)
    assert any("node 'a' is not reachable" in e for e in errors)


def test_unknown_node_and_start_with_incoming_edge():
    spec = _spec(
        [START, END_OK],
        [
            {"from_node": "s", "kind": "success", "to_node": "ghost"},
            {"from_node": "ok", "kind": "success", "to_node": "s"},
        ],
    )
    errors = validate_graph(spec, _ctx()).errors
    assert any("unknown node 'ghost'" in e for e in errors)
    assert any("End node 'ok' can only hand off" in e for e in errors)
    assert any("Start has no incoming" in e for e in errors)


def test_transition_types_carry_their_own_fields():
    cases = [
        ({"kind": "if", "to_node": "ok"}, "needs a condition"),
        ({"kind": "success", "to_node": "ok", "condition": "x"}, "only an if may set a condition"),
        ({"kind": "timeout", "to_node": "ok"}, "timeout_seconds"),
        ({"kind": "success", "to_node": "ok", "timeout_seconds": 5}, "timeout_seconds"),
        ({"kind": "failure", "to_node": "ok", "retry_max": 99}, "exceeds"),
        ({"kind": "success", "to_node": "ok", "retry_max": 1}, "only a failure transition"),
        ({"kind": "success"}, "needs to_node"),
    ]
    for extra, needle in cases:
        spec = _spec([START, END_OK], [{"from_node": "s", **extra}])
        errors = validate_graph(spec, _ctx()).errors
        assert any(needle in e for e in errors), (extra, errors)


def test_at_most_one_success_failure_else_timeout_per_node():
    spec = _spec(
        [START, END_OK, END_BAD],
        [
            {"from_node": "s", "kind": "success", "to_node": "ok"},
            {"from_node": "s", "kind": "success", "to_node": "bad"},
        ],
    )
    assert any("2 success transitions" in e for e in validate_graph(spec, _ctx()).errors)


def test_node_kinds_carry_exactly_their_reference():
    spec = _spec(
        [START, {"key": "p", "kind": "process"}, {"key": "e", "kind": "end"}, {"key": "m", "kind": "meta_skill"}], []
    )
    errors = validate_graph(spec, _ctx()).errors
    for needle in ("needs process_key", "needs end_outcome", "needs meta_skill_id"):
        assert any(needle in e for e in errors), needle


def test_references_must_resolve_in_this_company():
    spec = _spec(
        [
            START,
            {"key": "p", "kind": "process", "process_key": "nope"},
            {"key": "m", "kind": "meta_skill", "meta_skill_id": "nope"},
            END_OK,
        ],
        [],
    )
    errors = validate_graph(spec, _ctx()).errors
    assert any("process 'nope' does not exist" in e for e in errors)
    assert any("meta skill 'nope' does not exist" in e for e in errors)


def test_handoff_must_cross_roles_and_target_an_existing_workflow():
    def handoff(target):
        return _spec(
            [START, END_OK],
            [
                {"from_node": "s", "kind": "success", "to_node": "ok"},
                {"from_node": "ok", "kind": "handoff", "handoff_workflow_id": target},
            ],
        )

    assert any("must cross roles" in e for e in validate_graph(handoff("mine"), _ctx()).errors)
    assert any("does not exist" in e for e in validate_graph(handoff("ghost"), _ctx()).errors)
    assert any("owned by a role" in e for e in validate_graph(handoff("other"), _ctx(own_role_id=None)).errors)
    meta_target = _ctx(handoff_targets={"m": HandoffTarget("meta_skill", None)})
    assert any("does not exist" in e for e in validate_graph(handoff("m"), meta_target).errors)
    assert validate_graph(handoff("other"), _ctx()).errors == []


def test_handoff_does_not_make_the_graph_reachable_and_takes_no_node():
    spec = _spec(
        [START, END_OK],
        [
            {"from_node": "s", "kind": "success", "to_node": "ok"},
            {"from_node": "s", "kind": "handoff", "to_node": "ok", "handoff_workflow_id": "other"},
        ],
    )
    assert any("targets a workflow, not a node" in e for e in validate_graph(spec, _ctx()).errors)


def test_meta_skill_cannot_call_itself_directly_or_indirectly():
    call = {"key": "m", "kind": "meta_skill", "meta_skill_id": "meta1"}
    spec = _spec(
        [START, call, END_OK],
        [
            {"from_node": "s", "kind": "success", "to_node": "m"},
            {"from_node": "m", "kind": "success", "to_node": "ok"},
        ],
    )
    assert validate_graph(spec, _ctx(own_workflow_id="wf")).errors == []
    assert any("call itself" in e for e in validate_graph(spec, _ctx(own_workflow_id="meta1")).errors)
    ctx = _ctx(own_workflow_id="meta0", meta_skills=frozenset({"meta1"}), meta_calls={"meta1": frozenset({"meta0"})})
    assert any("calls back" in e for e in validate_graph(spec, ctx).errors)


def test_soft_findings_are_warnings_not_errors():
    spec = _spec(
        [START, {"key": "a", "kind": "process", "process_key": "p1"}, END_OK],
        [
            {"from_node": "s", "kind": "success", "to_node": "a"},
            {"from_node": "a", "kind": "if", "to_node": "ok", "condition": "x > 1"},
        ],
    )
    report = validate_graph(spec, _ctx(held_skills=frozenset()))
    assert report.errors == []
    assert any("no on-failure path" in w for w in report.warnings)
    assert any("if without an else" in w for w in report.warnings)
    assert any("does not hold skill 'sql'" in w for w in report.warnings)
