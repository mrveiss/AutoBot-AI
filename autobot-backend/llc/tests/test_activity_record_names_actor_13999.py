# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every activity-log ``record(`` call under ``llc/`` says who acted (#13999).

``LLCActivityLogService.record`` requires ``actor_type``. A call that omits it raises
``TypeError`` the moment a real log service is wired in, and one that guesses writes the
wrong actor into an append-only table. The call sites are parsed with ``ast`` so a call
spread over several lines counts the same as a one-liner.

A call is flagged when it has no ``actor_type`` keyword and fewer than three positional
arguments, or passes ``actor_type=None``. ``**kwargs`` forwarding is accepted only inside
``record_bulk`` itself. Only calls whose receiver looks like an activity log are examined. ``audit(log, session, ...)``
(``services/actor.py``) is held to the same rule, and is the one other place ``**entry`` may be forwarded.

What this still cannot see: a call through an alias (``rec = log.record; rec(...)``), a
receiver named something else, and the entries handed to ``record_bulk`` (each is a dict
that ``record_bulk`` forwards unchecked).

``EXEMPT`` names a file and the EXACT number of omissions it is allowed, so a second
omission in it fails; once the file is fixed the entry fails too and has to be deleted.
"""

import ast
import re
from pathlib import Path
from typing import Optional

LLC_ROOT = Path(__file__).resolve().parent.parent
# Positional order of LLCActivityLogService.record: session, company_id, actor_type, ...
ACTOR_TYPE_POSITION = 2
MIN_CALLS_EXPECTED = 40
FORWARDING_FUNCTIONS = {"record_bulk", "audit"}  # forward **entry on purpose; their callers are checked
_LOG_RECEIVER = re.compile(r"(^|\.|_)(activity_log|log)$|^(svc|self)$")

EXEMPT = {
    # file -> (allowed omissions, why)
    "scheduler/liveness_monitor.py": (1, "held by PR #19958 (scheduler/agents/replay are edited there)"),
}


def _is_none(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _omits_actor_type(call: ast.Call, enclosing: Optional[str]) -> bool:
    """True for an activity-log ``.record(...)`` call that supplies no real actor type."""
    for kw in call.keywords:
        if kw.arg == "actor_type":
            return _is_none(kw.value)
    if any(kw.arg is None for kw in call.keywords):  # **entry
        return enclosing not in FORWARDING_FUNCTIONS
    offset = 1 if isinstance(call.func, ast.Name) else 0  # audit(log, session, ...) has the log first
    return len(call.args) <= ACTOR_TYPE_POSITION + offset


def _is_record_call(node: ast.Call) -> bool:
    """``<activity log>.record(...)`` or the ``audit(log, session, ...)`` wrapper around it."""
    if isinstance(node.func, ast.Name):
        return node.func.id == "audit"
    return (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "record"
        and bool(_LOG_RECEIVER.search(ast.unparse(node.func.value)))
    )


def _record_calls(tree: ast.AST) -> list[tuple[ast.Call, Optional[str]]]:
    """Every ``<activity log>.record(...)`` call with the name of its enclosing function."""
    found = []

    def visit(node: ast.AST, enclosing: Optional[str]) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            enclosing = node.name
        if isinstance(node, ast.Call) and _is_record_call(node):
            found.append((node, enclosing))
        for child in ast.iter_child_nodes(node):
            visit(child, enclosing)

    visit(tree, None)
    return found


def _omissions_in(source: str) -> list[int]:
    return sorted(c.lineno for c, fn in _record_calls(ast.parse(source)) if _omits_actor_type(c, fn))


def _llc_files() -> list[Path]:
    return sorted(p for p in LLC_ROOT.rglob("*.py") if "__pycache__" not in p.parts)


def test_every_record_call_names_its_actor():
    offenders = []
    for path in _llc_files():
        rel = path.relative_to(LLC_ROOT).as_posix()
        lines = _omissions_in(path.read_text(encoding="utf-8"))
        if rel in EXEMPT:
            allowed, _why = EXEMPT[rel]
            if len(lines) > allowed:
                offenders += [f"{rel}:{n} (allowed {allowed})" for n in lines]
            continue
        offenders += [f"{rel}:{n}" for n in lines]
    assert not offenders, f"record() without actor_type (#13999): {offenders}"


def test_exemptions_are_exact():
    for rel, (allowed, reason) in EXEMPT.items():
        found = _omissions_in((LLC_ROOT / rel).read_text(encoding="utf-8"))
        assert len(found) == allowed, f"{rel} has {len(found)} omissions, entry allows {allowed} ({reason}); update it"


def test_population_is_not_empty_and_matches_a_second_derivation():
    """A guard over zero calls passes; cross-check the AST population against plain text."""
    this_file = Path(__file__).resolve()  # its planted controls contain ".record(" as text
    ast_files, total = set(), 0
    for path in _llc_files():
        if path == this_file:
            continue
        calls = _record_calls(ast.parse(path.read_text(encoding="utf-8")))
        total += len(calls)
        if calls:
            ast_files.add(path)
    text_files = {
        p for p in _llc_files() if p != this_file and re.search(r"\.record\(|\baudit\(", p.read_text(encoding="utf-8"))
    }
    assert total >= MIN_CALLS_EXPECTED, f"only {total} record() calls found; the walk is broken"
    assert text_files == ast_files, f"text/AST disagree: {sorted(p.name for p in text_files ^ ast_files)}"


CONTROLS_OMITTING = {
    "one line": "async def f(s):\n    await log.record(s, company_id='c', actor_id='a', event_type='e')\n",
    "multi line": "async def f(s):\n    await self.activity_log.record(\n        s,\n        company_id='c',\n    )\n",
    "positional session and company only": "async def f(s):\n    await log.record(s, 'c', event_type='e')\n",
    "conditional wrapper": (
        "async def f(s):\n    if self.activity_log:\n        await self.activity_log.record(session=s)\n"
    ),
    "actor_type None": "async def f(s):\n    await log.record(s, actor_type=None)\n",
    "audit() without an actor": "async def f(s):\n    await audit(log, s, company_id='c')\n",
    "forwarding outside record_bulk": "async def f(s, **e):\n    await log.record(session=s, **e)\n",
}
CONTROLS_NAMING = {
    "keyword": "async def f(s):\n    await log.record(s, actor_type=ActorType.USER)\n",
    "positional": "async def f(s):\n    await log.record(s, 'c', ActorType.USER, 'a')\n",
    "forwarding inside record_bulk": "async def record_bulk(s, **e):\n    await self.record(session=s, **e)\n",
    "audit() naming the actor": "async def f(s):\n    await audit(log, s, actor_type=ActorType.USER)\n",
    "forwarding inside audit": "async def audit(log, s, **e):\n    await log.record(s, **e)\n",
    "receiver is not a log": "async def f(s):\n    metrics.record(s)\n",
}


def test_guard_catches_planted_omissions_of_every_shape():
    for shape, source in CONTROLS_OMITTING.items():
        assert _omissions_in(source), f"guard missed a planted {shape} call"


def test_guard_does_not_flag_calls_that_name_the_actor():
    for shape, source in CONTROLS_NAMING.items():
        assert not _omissions_in(source), f"guard flagged a correct {shape} call"


# --- behaviour: the fixed call sites hand the real log a real actor -------------------------
import uuid  # noqa: E402
from unittest.mock import AsyncMock, MagicMock  # noqa: E402

import pytest  # noqa: E402

from llc.models.activity import ActorType  # noqa: E402
from llc.services.actor import resolve_actor  # noqa: E402

_USER, _AGENT = str(uuid.uuid4()), str(uuid.uuid4())


def test_resolve_actor_user_beats_agent_and_nothing_is_system():
    assert resolve_actor(_AGENT, _USER)[:2] == (ActorType.USER, _USER)
    assert resolve_actor(_AGENT, None)[:2] == (ActorType.AGENT, _AGENT)
    assert resolve_actor()[:2] == (ActorType.SYSTEM, None)


def test_resolve_actor_never_hands_record_a_non_uuid_and_keeps_the_identity():
    who = resolve_actor(user_id="service-key")
    assert (who.type, who.id) == (ActorType.SYSTEM, None)
    assert who.metadata({"k": 1}) == {"k": 1, "claimed_actor": "service-key", "claimed_actor_type": "user"}
    assert resolve_actor(_AGENT).metadata() is None


def _session_with(obj):
    session = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = obj
    session.execute = AsyncMock(return_value=result)
    session.get = AsyncMock(return_value=None)
    return session


@pytest.mark.asyncio
async def test_goal_create_records_the_acting_user_else_system():
    from llc.models.goal import GoalLevel
    from llc.services.goal import GoalService

    for kwargs, expected in (
        ({"actor_user_id": _USER}, (ActorType.USER, _USER)),
        ({"actor_agent_id": _AGENT}, (ActorType.AGENT, _AGENT)),
        ({}, (ActorType.SYSTEM, None)),
    ):
        log = MagicMock(record=AsyncMock())
        svc = GoalService(activity_log=log)
        svc._schedule_post_commit_index = MagicMock()
        await svc.create(_session_with(None), str(uuid.uuid4()), "t", GoalLevel.OBJECTIVE, **kwargs)
        sent = log.record.await_args.kwargs
        assert (sent["actor_type"], sent["actor_id"]) == expected


@pytest.mark.asyncio
async def test_label_assign_and_remove_record_the_acting_user():
    from llc.services.label_service import LLCLabelService

    work_item = MagicMock(company_id=uuid.uuid4())
    log = MagicMock(record=AsyncMock())
    svc = LLCLabelService(activity_log=log)
    session = _session_with(work_item)
    await svc.assign_labels(session, str(uuid.uuid4()), [str(uuid.uuid4())], actor_user_id=_USER)
    await svc.remove_label(session, str(uuid.uuid4()), str(uuid.uuid4()), actor_user_id=_USER)
    for call in log.record.await_args_list:
        assert call.kwargs["actor_type"] == ActorType.USER and call.kwargs["actor_id"] == _USER
        assert "after_state" not in call.kwargs  # record() takes `after`


@pytest.mark.asyncio
async def test_relations_add_and_remove_record_the_actor_and_keep_their_metadata():
    from llc.models.enums import WorkItemRelationType
    from llc.services.work_item_relations import WorkItemRelationService

    log = MagicMock(record=AsyncMock())
    svc = WorkItemRelationService(activity_log=log)
    svc._insert_one = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
    cid, src, tgt = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    await svc.add(
        MagicMock(flush=AsyncMock()),
        company_id=cid,
        source_id=src,
        target_id=tgt,
        relation_type=WorkItemRelationType.RELATES_TO,
        created_by_agent_id=_AGENT,
    )
    added = log.record.await_args.kwargs
    assert (added["actor_type"], added["actor_id"]) == (ActorType.AGENT, _AGENT)
    assert added["metadata"]["target_id"] == tgt

    rel = MagicMock(source_id=uuid.UUID(src), target_id=uuid.UUID(tgt), relation_type="relates_to")
    session = _session_with(rel)
    session.delete = AsyncMock()
    await svc.remove(session, company_id=cid, relation_id=str(uuid.uuid4()), actor_user_id="service-key")
    removed = log.record.await_args.kwargs
    assert (removed["actor_type"], removed["actor_id"]) == (ActorType.SYSTEM, None)
    assert removed["metadata"]["claimed_actor"] == "service-key" and removed["metadata"]["target_id"] == tgt


@pytest.mark.asyncio
async def test_transition_to_done_records_the_actor_and_survives_a_service_principal():
    from llc.models.enums import WorkItemStatus
    from llc.services import work_item_service as wis

    can_finish = next(st for st, to in wis._ALLOWED_TRANSITIONS.items() if WorkItemStatus.DONE in to)
    for kwargs, expected_type, expected_id in (
        ({"actor_user_id": _USER}, ActorType.USER, _USER),
        ({"actor_agent_id": _AGENT}, ActorType.AGENT, _AGENT),
        ({"actor_user_id": "service-key"}, ActorType.SYSTEM, None),
    ):
        log = MagicMock(record=AsyncMock())
        svc = wis.WorkItemService(activity_log=log)
        svc._trigger_artifact_ingest = AsyncMock()
        item = MagicMock(status=can_finish.value, version=1)
        await svc.transition_to_done(_session_with(item), str(uuid.uuid4()), str(uuid.uuid4()), **kwargs)
        sent = log.record.await_args.kwargs
        assert (sent["actor_type"], sent["actor_id"]) == (expected_type, expected_id)


@pytest.mark.asyncio
async def test_coworking_with_a_service_principal_is_recorded_as_system_not_a_failure():
    from llc.services.work_item_service import WorkItemService

    log = MagicMock(record=AsyncMock())
    svc = WorkItemService(activity_log=log)
    item = MagicMock(co_worker_type=None, co_worker_agent_id=None, co_worker_user_id=None, version=1)
    await svc.enable_coworking(
        _session_with(item),
        work_item_id=str(uuid.uuid4()),
        co_worker_type="agent",
        company_id=str(uuid.uuid4()),
        co_worker_agent_id=_AGENT,
        actor_id="svc-principal",
        actor_type="agent",
        caller_role="owner",
    )
    sent = log.record.await_args.kwargs
    assert (sent["actor_type"], sent["actor_id"]) == (ActorType.SYSTEM, None)
    assert sent["metadata"] == {"claimed_actor": "svc-principal", "claimed_actor_type": "agent"}


@pytest.mark.asyncio
async def test_secret_actor_is_the_authenticated_caller_and_a_forged_one_cannot_fail_the_write():
    from llc.services.secret import SecretService

    log = MagicMock(record=AsyncMock())
    svc = SecretService(activity_log=log)
    svc._fernet = MagicMock(return_value=MagicMock(encrypt=MagicMock(return_value=b"x")))
    session = _session_with(MagicMock(id=uuid.uuid4(), version=1))
    await svc.set(session, str(uuid.uuid4()), "n", "v", _USER)
    sent = log.record.await_args.kwargs
    assert (sent["actor_type"], sent["actor_id"]) == (ActorType.USER, _USER)
    await svc.set(session, str(uuid.uuid4()), "n", "v", "not-a-uuid")
    forged = log.record.await_args.kwargs
    assert (forged["actor_type"], forged["actor_id"]) == (ActorType.SYSTEM, None)
    assert forged["metadata"]["claimed_actor"] == "not-a-uuid"
