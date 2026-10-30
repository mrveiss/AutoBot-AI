# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every activity-log ``record(`` call under ``llc/`` says who acted (#13999).

``LLCActivityLogService.record`` requires ``actor_type``. A call that omits it raises
``TypeError`` the moment a real log service is wired in, and one that guesses writes the
wrong actor into an append-only table. The call sites are parsed with ``ast`` so a call
spread over several lines counts the same as a one-liner.

``# type: ignore``-style exemptions do not exist here. ``EXEMPT`` names a file, the issue
holding its fix, and must still contain an omission: once the file is fixed the entry
fails this test and has to be deleted, so the exemption cannot outlive its reason.
"""

import ast
import re
from pathlib import Path

LLC_ROOT = Path(__file__).resolve().parent.parent
# Positional order of LLCActivityLogService.record: session, company_id, actor_type, ...
ACTOR_TYPE_POSITION = 2
MIN_CALLS_EXPECTED = 40

EXEMPT = {
    "scheduler/liveness_monitor.py": "held by PR #19958 (scheduler/agents/replay are edited there)",
}


def _omits_actor_type(call: ast.Call) -> bool:
    """True for a ``.record(...)`` call that supplies no actor type by any route."""
    if any(kw.arg == "actor_type" for kw in call.keywords):
        return False
    if any(kw.arg is None for kw in call.keywords):  # **entry: forwarded wholesale (record_bulk)
        return False
    return len(call.args) <= ACTOR_TYPE_POSITION


def _record_calls(tree: ast.AST) -> list[ast.Call]:
    return [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "record"
    ]


def _omissions_in(source: str) -> list[int]:
    return sorted(c.lineno for c in _record_calls(ast.parse(source)) if _omits_actor_type(c))


def _llc_files() -> list[Path]:
    return sorted(p for p in LLC_ROOT.rglob("*.py") if "__pycache__" not in p.parts)


def test_every_record_call_names_its_actor():
    offenders = []
    for path in _llc_files():
        rel = path.relative_to(LLC_ROOT).as_posix()
        if rel in EXEMPT:
            continue
        lines = _omissions_in(path.read_text(encoding="utf-8"))
        offenders += [f"{rel}:{n}" for n in lines]
    assert not offenders, f"record() without actor_type (#13999): {offenders}"


def test_exemptions_still_have_an_omission():
    for rel, reason in EXEMPT.items():
        found = _omissions_in((LLC_ROOT / rel).read_text(encoding="utf-8"))
        assert found, f"{rel} is fixed ({reason}); delete its EXEMPT entry"


def test_population_is_not_empty_and_matches_a_second_derivation():
    """A guard over zero calls passes; cross-check the AST population against plain text."""
    ast_files, total = set(), 0
    for path in _llc_files():
        calls = _record_calls(ast.parse(path.read_text(encoding="utf-8")))
        total += len(calls)
        if calls and path != Path(__file__).resolve():
            ast_files.add(path)
    this_file = Path(__file__).resolve()  # its planted controls contain ".record(" as text
    text_files = {p for p in _llc_files() if p != this_file and re.search(r"\.record\(", p.read_text(encoding="utf-8"))}
    assert total >= MIN_CALLS_EXPECTED, f"only {total} record() calls found; the walk is broken"
    assert text_files == ast_files, f"text/AST disagree: {sorted(p.name for p in text_files ^ ast_files)}"


CONTROLS_OMITTING = {
    "one line": "async def f(s):\n    await log.record(s, company_id='c', actor_id='a', event_type='e')\n",
    "multi line": "async def f(s):\n    await self.activity_log.record(\n        s,\n        company_id='c',\n    )\n",
    "positional session and company only": "async def f(s):\n    await log.record(s, 'c', event_type='e')\n",
    "conditional wrapper": (
        "async def f(s):\n    if self.activity_log:\n        await self.activity_log.record(session=s)\n"
    ),
}
CONTROLS_NAMING = {
    "keyword": "async def f(s):\n    await log.record(s, actor_type=ActorType.USER)\n",
    "positional": "async def f(s):\n    await log.record(s, 'c', ActorType.USER, 'a')\n",
    "forwarded kwargs": "async def f(s, **e):\n    await log.record(session=s, **e)\n",
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
    assert resolve_actor(_AGENT, _USER) == (ActorType.USER, _USER)
    assert resolve_actor(_AGENT, None) == (ActorType.AGENT, _AGENT)
    assert resolve_actor() == (ActorType.SYSTEM, None)


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
async def test_secret_set_records_the_acting_agent():
    from llc.services.secret import SecretService

    log = MagicMock(record=AsyncMock())
    svc = SecretService(activity_log=log)
    svc._fernet = MagicMock(return_value=MagicMock(encrypt=MagicMock(return_value=b"x")))
    secret = MagicMock(id=uuid.uuid4(), version=1)
    session = _session_with(secret)
    await svc.set(session, str(uuid.uuid4()), "n", "v", _AGENT)
    sent = log.record.await_args.kwargs
    assert (sent["actor_type"], sent["actor_id"]) == (ActorType.AGENT, _AGENT)
