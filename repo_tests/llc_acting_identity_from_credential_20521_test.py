# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A Company OS route never takes the acting identity from the request (#20521).

The acting user or agent is the authenticated session's or credential's. A route that records a
requester, creator, author, uploader or reviewer from a body or query field lets any caller put anyone's
name on the act. The detector (``_acting_identity_detect``) reads the syntax tree of ``llc/api``.

Frozen baseline: EMPTY (``_BASELINE``). Every instance found was fixed rather than listed. What remains
in ``_SUBJECTS`` is not a baseline of defects: each entry is a field naming who is being ACTED ON or
FILTERED BY (the person asked to review, the actor a listing is filtered to), with the reason beside it.

Vocabulary limit, stated beside the baseline: "EMPTY" means empty in the detector's vocabulary only -- a field
whose NAME says who acted (``actor``, ``*_by``, ``author_*``, ``reviewer_*``). It does not cover the whole class.
A plain ``agent_id`` / ``user_id`` is not scanned by name, and these known instances are out of vocabulary and
NOT fixed here (they need an owner decision, tracked on #20521): ``CheckoutRequest.agent_id`` and
``ReleaseRequest.agent_id`` (``llc/api/work_items.py``), and the requester of ``api/approval_gates.py``
(outside the scanned package).

Boundary, stated where it is read: route modules under ``autobot-backend/llc/api``; request models are
resolved by class name across that package; a model defined elsewhere, a handler registered without a
``router.<verb>`` decorator, and a raw ``await request.json()`` are not seen.
"""

from __future__ import annotations

import functools

import pytest
from repo_tests._acting_identity_detect import (
    Finding,
    collect_models,
    declared_actor_fields,
    parse_all,
    scan,
    unresolved_annotations,
)
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared.testfile_names import is_test_filename
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_API = "autobot-backend/llc/api"

#: Frozen at EMPTY: nothing is exempt for being unfixed.
_BASELINE: frozenset[Finding] = frozenset()

#: Fields that name who is acted on or filtered by, never who acts: ``(path, route, field)`` -> why.
_SUBJECTS = {
    (f"{_API}/activity.py", "get_activity_log", "actor_type"): "a filter: the kind of actor to list",
    (f"{_API}/activity.py", "get_activity_log", "actor_id"): "a filter: the actor whose entries to list",
    (f"{_API}/work_items.py", "list_work_items", "reviewer"): "a filter: items awaiting this reviewer",
    (f"{_API}/work_items.py", "handoff_to_human", "reviewer_user_id"): "who is being asked; checked to be a member",
    (f"{_API}/review_gate_policies.py", "create_review_gate_policy", "reviewer_role"): "policy data: the review role",
    (f"{_API}/review_gate_policies.py", "update_review_gate_policy", "reviewer_role"): "policy data: the review role",
}

#: Declared actor-named request fields the detector must SEE: the first is never valued, the second is valued
#: and recorded in `_SUBJECTS` (who is being asked, not who is acting).
_KNOWN_SHIMS = {
    ("ApprovalDecision", "decided_by_agent_id"),
    ("HandoffToHumanRequest", "reviewer_user_id"),
}

#: Fields #20521 removed from the request models; none may come back.
_REMOVED = {
    ("ApprovalRequest", "requested_by_agent_id"),
    ("WorkItemCreate", "created_by_agent_id"),
    ("CommentCreate", "author_user_id"),
    ("CommentCreate", "author_agent_id"),
    ("LabelCreate", "created_by"),
    ("LabelAssign", "assigned_by"),
    ("SecretSetRequest", "actor"),
    ("RelationCreate", "created_by_agent_id"),
    ("RelationCreate", "created_by_user_id"),
    ("SprintCloseRequest", "decided_by"),
}

_REQUEST_SUFFIXES = ("Request", "Create", "Update", "Body", "Payload", "Input")


def _population(root) -> list[str]:  # noqa: ANN001
    try:
        tracked = tracked_paths(root, _API)
    except EmptyEnumeration:
        return []
    return [r for r in tracked if r.endswith(".py") and "/tests/" not in r and not is_test_filename(r)]


REACH = declare(
    "llc-api-acting-identity",
    discover=_population,
    what="route modules",
    roots=(_API,),
    growth=20,
)


#: Modules that define request models the routes import: resolved, not scanned for routes.
_MODEL_MODULES = ("autobot-backend/llc/models", "autobot-backend/api/schemas_agent.py")


@functools.lru_cache(maxsize=1)
def _sources() -> dict[str, str]:
    root = repo_root()
    return {r: (root / r).read_text(encoding="utf-8") for r in REACH.examined(root)}


@functools.lru_cache(maxsize=1)
def _model_sources() -> dict[str, str]:
    root = repo_root()
    paths = [p for p in tracked_paths(root, *_MODEL_MODULES) if p.endswith(".py")]
    return {p: (root / p).read_text(encoding="utf-8") for p in paths}


# -- the detector, against every mechanism a request value can reach a service by ----------------------

_MODEL = "class Body(BaseModel):\n    name: str\n    created_by: str | None = None\n"
_ROUTE = '@router.post("/x")\nasync def route(body: Body):\n    {stmt}\n'


def _found(source: str, extra: dict[str, str] | None = None) -> list[Finding]:
    return scan({"routes.py": source, **(extra or {})})


@pytest.mark.parametrize(
    ("label", "stmt", "how"),
    [
        ("a keyword argument", "svc.create(created_by=body.created_by)", "attr"),
        ("an assignment", "who = body.created_by", "attr"),
        ("a default fallback", "who = body.created_by or me", "attr"),
        ("a model dump", "svc.create(**body.model_dump())", "dump"),
        ("the whole model handed on", "svc.create(body)", "whole"),
        ("a getattr read", 'svc.create(getattr(body, "created_by"))', "whole"),
    ],
)
def test_every_way_a_route_can_value_a_request_actor_is_found(label: str, stmt: str, how: str) -> None:
    (finding,) = _found(_MODEL + _ROUTE.format(stmt=stmt))
    assert (finding.function, finding.how) == ("route", how), label


def test_a_helper_that_values_the_field_is_followed() -> None:
    helper = "def _make(b):\n    return b.created_by\n\n"
    (finding,) = _found(_MODEL + helper + _ROUTE.format(stmt="_make(body)"))
    assert (finding.function, finding.field, finding.how) == ("route", "created_by", "attr")


def test_an_inherited_actor_field_is_found() -> None:
    child = "class Child(Body):\n    extra: int = 0\n\n"
    source = _MODEL + child + "@router.post('/y')\nasync def r(b: Child):\n    use(b.created_by)\n"
    assert [f.function for f in _found(source)] == ["r"]


def test_a_model_defined_in_another_module_is_found() -> None:
    route = '@router.post("/x")\nasync def route(body: Body):\n    svc.create(body.created_by)\n'
    assert [f.function for f in _found(route, {"models.py": _MODEL})] == ["route"]


@pytest.mark.parametrize(
    ("label", "params"),
    [
        ("an un-annotated parameter beside it", "other, body: Body"),
        ("Optional[...]", "body: Optional[Body] = None"),
        ("Body | None", "body: Body | None = None"),
        ("Annotated[...]", "body: Annotated[Body, Depends(dep)]"),
        ("a dotted name", "body: schemas.Body"),
        ("a string annotation", 'body: "Body"'),
        ("a keyword-only parameter", "*, body: Body"),
        ("a positional-only parameter", "body: Body, /"),
        ("a parameter with a Depends default", "x: int = Depends(dep), body: Body = None"),
    ],
)
def test_the_model_is_found_however_its_annotation_is_wrapped(label: str, params: str) -> None:
    source = _MODEL + f'@router.post("/x")\nasync def route({params}):\n    svc.create(body.created_by)\n'
    assert [f.function for f in _found(source)] == ["route"], label


def test_a_sync_route_and_a_nested_function_are_read() -> None:
    source = _MODEL + '@router.post("/x")\ndef route(body: Body):\n    def inner():\n        return body.created_by\n'
    assert [f.function for f in _found(source)] == ["route"]


def test_an_audit_log_record_call_is_not_a_log_call() -> None:
    stmt = "log.record(session, actor_id=body.created_by)"
    assert [f.how for f in _found(_MODEL + _ROUTE.format(stmt=stmt))] == ["attr"]


def test_a_model_passed_to_a_helper_that_swallows_it_in_kwargs_is_a_use() -> None:
    helper = "def _make(**kw):\n    return kw\n\n"
    assert [f.how for f in _found(_MODEL + helper + _ROUTE.format(stmt="_make(b=body)"))] == ["whole"]


def test_an_actor_named_query_parameter_that_is_used_is_found() -> None:
    source = '@router.get("/x")\nasync def route(created_by: str | None = None):\n    svc.list(created_by)\n'
    (finding,) = _found(source)
    assert (finding.field, finding.how) == ("created_by", "param")


@pytest.mark.parametrize(
    ("label", "stmt"),
    [
        ("compared only", "ok = body.created_by is not None"),
        ("tested for truth only", "if body.created_by:\n        pass"),
        ("logged only", 'logger.warning("ignoring %s", body.created_by)'),
        ("a field that names no actor", "svc.create(body.name)"),
    ],
)
def test_a_field_that_is_only_looked_at_is_not_a_use(label: str, stmt: str) -> None:
    assert _found(_MODEL + _ROUTE.format(stmt=stmt)) == [], label


def test_a_helper_that_only_compares_and_logs_is_not_a_use() -> None:
    helper = "def _look(b):\n    if b.created_by is not None:\n        logger.warning('x %s', b.created_by)\n\n"
    assert _found(_MODEL + helper + _ROUTE.format(stmt="_look(body)")) == []


def test_a_response_model_and_a_plain_function_are_not_request_inputs() -> None:
    response = "class Out(BaseModel):\n    created_by: str\n\n"
    plain = "def helper(body: Body):\n    return body.created_by\n"
    assert _found(_MODEL + response + plain + _ROUTE.format(stmt="return Out(created_by='x')")) == []


def test_an_unused_actor_named_parameter_is_not_a_use() -> None:
    source = '@router.get("/x")\nasync def route(created_by: str | None = None):\n    return 1\n'
    assert _found(source) == []


# -- the tree --------------------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _findings() -> tuple[Finding, ...]:
    return tuple(scan(_sources(), _model_sources()))


def _models(trees: dict) -> dict[str, set[str]]:
    return collect_models([*trees.values(), *parse_all(_model_sources()).values()])


def _unexplained() -> list[Finding]:
    return [f for f in _findings() if (f.path, f.function, f.field) not in _SUBJECTS and f not in _BASELINE]


def test_no_route_takes_the_acting_identity_from_the_request() -> None:
    assert not _unexplained(), (
        f"#20521: {_unexplained()} value a request field that names the actor. Take the actor from the "
        "authenticated session (llc.api._common.acting_user_id / actor_id) and drop the field from the model."
    )


def test_every_subject_entry_still_matches_a_use() -> None:
    seen = {(f.path, f.function, f.field) for f in _findings()}
    assert not set(_SUBJECTS) - seen, f"stale _SUBJECTS entries, remove them: {sorted(set(_SUBJECTS) - seen)}"


def test_the_detector_sees_the_known_actor_fields_and_none_of_the_removed_ones() -> None:
    trees = parse_all(_sources())
    declared = declared_actor_fields(trees, _models(trees))
    assert _KNOWN_SHIMS <= declared, f"the detector no longer sees {sorted(_KNOWN_SHIMS - declared)}: it is blind"
    assert not _REMOVED & declared, f"removed actor fields are back: {sorted(_REMOVED & declared)}"


def test_no_request_model_is_defined_outside_the_scanned_package() -> None:
    trees = parse_all(_sources())
    unresolved = unresolved_annotations(trees, _models(trees))
    outside = sorted(n for n in unresolved if n not in _REQUEST_SUFFIXES and n.endswith(_REQUEST_SUFFIXES))
    assert not outside, f"route parameters annotated with models the scan cannot resolve: {outside}"
