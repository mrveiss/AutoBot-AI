# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A Company OS write route commits before it answers (#21332, owner ruling 2026-11-21).

A 2xx from an llc write route means the write is committed. One dependency carries that: `llc.deps.session_dep`
(`get_session` resolved with FastAPI's `scope="function"`, which exits after the route body and before the response
is sent). Four parts pin it, each next to the control that proves its instrument can fail:

* G1  behavioural: a real ASGI call records `commit` before `http.response.start`; the default scope (control) shows
      the opposite, so a FastAPI change or a broken harness is reported as such.
* G2  structural: every write route of the real `llc.api.router` resolves its session through that one dependency,
      read from FastAPI's own resolved dependency tree (decorator- and router-level `dependencies=` included).
      The visited routes must equal, as sets, the routes derived from the decorators in source.
* G3  declared boundary: the write routes with no request session are an exact, named list.
* G4  AST: no `except` rolls back or guards a commit and then falls through to a normal return.

The files still held back by an open PR sit in `_commit_before_answer_baseline.py`, shrink-only. The mounted-app
question is answered by the closest canonical alternative: importing the whole backend app is not possible in a
test (its lifespan needs Postgres and Redis), so G2 walks the aggregated `llc.api.router` and a separate assertion
reads `FEATURE_ROUTER_CONFIGS` for the mount.
"""

import ast
from typing import Annotated
from unittest.mock import patch

import pytest
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from repo_tests._paths import repo_root
from repo_tests._ratchet_base import base_file_present, base_table
from sqlalchemy.ext.asyncio import AsyncSession

from llc.api import router as llc_router
from llc.deps import get_session, session_dep
from llc.tests._commit_before_answer import (
    LLC_ROOT,
    OWN_SESSION_HANDLERS,
    REPO_ROOT,
    baseline_additions,
    decorated_write_routes,
    llc_write_routes,
    route_key,
    session_violations,
    sessionless_routes,
    source_write_routes,
    stale_entries,
    swallowed_failures,
    swallowed_failures_in_tree,
    violating_files,
)
from llc.tests._commit_before_answer_baseline import COMMIT_BEFORE_ANSWER_BASELINE
from testkit.fake_async_session import FakeAsyncSession
from user_management.database import get_async_session

#: Measured 190 write routes on origin/main (2026-11-21); a floor, so a router dropped from the aggregate is loud.
_WRITE_ROUTE_FLOOR = 185
_BASELINE_REL = "autobot-backend/llc/tests/_commit_before_answer_baseline.py"

# ---------------------------------------------------------------------------
# G1: the order of events in a real ASGI call
# ---------------------------------------------------------------------------


def _recorded(events: list, name: str, original):  # noqa: ANN001, ANN202
    async def call(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        events.append(name)
        return await original(*args, **kwargs)

    return call


def _recording_session(events: list, fail_commit: bool) -> FakeAsyncSession:
    """The canonical fake session, with its commit/rollback/close appended to *events* in call order."""
    session = FakeAsyncSession(commit_error=RuntimeError("commit failed") if fail_commit else None)
    for name in ("commit", "rollback", "close"):
        setattr(session, name, _recorded(events, name, getattr(session, name)))
    return session


def _scope(path: str) -> dict:
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"t")],
        "client": ("c", 1),
        "server": ("t", 80),
    }


def _app(events: list) -> FastAPI:
    app = FastAPI()

    @app.post("/scoped")
    async def scoped(session: AsyncSession = session_dep) -> dict:
        events.append("handler")
        return {"ok": True}

    @app.post("/default")
    async def default(session: AsyncSession = Depends(get_session)) -> dict:
        events.append("handler")
        return {"ok": True}

    @app.post("/refused")
    async def refused(session: AsyncSession = session_dep) -> dict:
        events.append("handler")
        raise HTTPException(status_code=409, detail="refused")

    return app


async def _call(path: str, *, fail_commit: bool = False) -> tuple[list, int | None, Exception | None]:
    """One real ASGI request; `events` interleaves the session's and the response's order."""
    events: list = []
    status: list = []

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict) -> None:
        if message["type"] == "http.response.start":
            events.append("http.response.start")
            status.append(message["status"])

    error: Exception | None = None
    with patch("llc.deps.get_async_session_factory", return_value=lambda: _recording_session(events, fail_commit)):
        try:
            await _app(events)(_scope(path), receive, send)
        except Exception as exc:  # noqa: BLE001 -- a failing commit is re-raised by the server error middleware
            error = exc
    return events, (status[0] if status else None), error


@pytest.mark.asyncio
async def test_the_session_commits_before_the_response_starts() -> None:
    events, status, error = await _call("/scoped")
    assert (status, error) == (200, None)
    assert events.index("commit") < events.index("http.response.start"), events
    assert events[:2] == ["handler", "commit"], events


@pytest.mark.asyncio
async def test_control_a_default_scope_session_commits_after_the_response_starts() -> None:
    """The control: the same route with a plain `Depends(get_session)` shows the defect this guard prevents.

    If this fails, FastAPI's default scope changed or the harness no longer observes the order: the ordering test
    above proves nothing until this one is understood.
    """
    events, status, _ = await _call("/default")
    assert status == 200
    assert events.index("http.response.start") < events.index("commit"), events


@pytest.mark.asyncio
async def test_a_failing_commit_never_reaches_the_client_as_a_2xx() -> None:
    events, status, error = await _call("/scoped", fail_commit=True)
    assert status is not None and status >= 500, (status, events)
    assert isinstance(error, RuntimeError) and "rollback" in events, (error, events)


@pytest.mark.asyncio
async def test_a_refusing_route_rolls_back_and_never_commits() -> None:
    events, status, _ = await _call("/refused")
    assert status == 409 and "commit" not in events, (status, events)
    assert events[:2] == ["handler", "rollback"], events


# ---------------------------------------------------------------------------
# G2: every write route resolves the function-scoped dependency
# ---------------------------------------------------------------------------


async def _direct(session: AsyncSession = Depends(get_session)) -> dict:
    return {}


def _service_with_session(session: AsyncSession = Depends(get_session)) -> object:
    return object()


async def _through_sub_dependency(service: object = Depends(_service_with_session)) -> dict:
    return {}


async def _annotated(session: Annotated[AsyncSession, Depends(get_session)]) -> dict:
    return {}


async def _legacy_provider(session: AsyncSession = Depends(get_async_session)) -> dict:
    return {}


def _service_with_scoped_session(session: AsyncSession = session_dep) -> object:
    return object()


async def _through_scoped_sub_dependency(service: object = Depends(_service_with_scoped_session)) -> dict:
    return {}


async def _scoped(session: AsyncSession = session_dep) -> dict:
    return {}


async def _no_session() -> dict:
    return {}


def _route(handler, **kwargs):  # noqa: ANN001, ANN202
    router = APIRouter(**kwargs)
    router.add_api_route("/x", handler, methods=["POST"])
    return router.routes[0]


_POSITIVES = [
    ("request_scoped_direct", _direct),
    ("session_only_through_a_sub_dependency", _through_sub_dependency),
    ("annotated_spelling", _annotated),
    ("legacy_get_async_session", _legacy_provider),
]
_CLEAN = [
    ("function_scoped_direct", _scoped),
    ("function_scoped_through_a_sub_dependency", _through_scoped_sub_dependency),
]


@pytest.mark.parametrize("handler", [h for _, h in _POSITIVES], ids=[i for i, _ in _POSITIVES])
def test_the_walk_reports_every_known_positive_shape(handler) -> None:  # noqa: ANN001
    assert session_violations(_route(handler))


@pytest.mark.parametrize("handler", [h for _, h in _CLEAN], ids=[i for i, _ in _CLEAN])
def test_the_walk_is_quiet_on_the_function_scoped_dependency(handler) -> None:  # noqa: ANN001
    assert session_violations(_route(handler)) == []


def test_the_walk_reads_a_router_level_dependency() -> None:
    route = _route(_no_session, dependencies=[Depends(_service_with_session)])
    assert session_violations(route), "a session reached only through router-level dependencies= must be walked"


@pytest.fixture(scope="module")
def routes() -> list:
    return llc_write_routes(llc_router)


def test_the_floor_is_read_only_after_the_positives_fire(routes: list) -> None:
    assert all(session_violations(_route(h)) for _, h in _POSITIVES), "the instrument must fire before it is counted"
    assert (
        len(routes) >= _WRITE_ROUTE_FLOOR
    ), f"{len(routes)} write routes visited, below the floor {_WRITE_ROUTE_FLOOR}"


def test_the_visited_routes_are_the_routes_declared_in_source(routes: list) -> None:
    """Sets, not counts: a router left out of `llc.api.router` shows up as a name, not a smaller total."""
    visited, declared = {route_key(r) for r in routes}, source_write_routes()
    assert visited == declared, f"not visited: {sorted(declared - visited)}; not declared: {sorted(visited - declared)}"


def test_the_llc_router_is_mounted_by_the_feature_registry() -> None:
    source = (REPO_ROOT / "autobot-backend/initialization/router_registry/feature_routers.py").read_text("utf-8")
    table = next(
        n.value
        for n in ast.walk(ast.parse(source))
        if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", "") == "FEATURE_ROUTER_CONFIGS"
    )
    mounted = [e.elts[0].value for e in table.elts if isinstance(e, ast.Tuple) and isinstance(e.elts[0], ast.Constant)]
    assert "llc.api" in mounted, "llc.api is no longer mounted: the route graph G2 walks is not the served one"


def test_every_write_route_commits_before_it_answers_except_the_baselined_files(routes: list) -> None:
    held = set(COMMIT_BEFORE_ANSWER_BASELINE)
    offenders = {
        route_key(r): session_violations(r) for r in routes if session_violations(r) and route_key(r)[0] not in held
    }
    assert not offenders, f"use `session_dep` from llc.deps (function scope): {sorted(offenders)}"


# ---------------------------------------------------------------------------
# The baseline: shrink-only, file-level
# ---------------------------------------------------------------------------


def test_the_baseline_names_exactly_the_files_that_still_violate(routes: list) -> None:
    measured, held = violating_files(routes), set(COMMIT_BEFORE_ANSWER_BASELINE)
    assert measured == held, f"unlisted violators: {sorted(measured - held)}; stale entries: {sorted(held - measured)}"


def test_no_file_was_added_to_the_baseline_against_the_base() -> None:
    root = repo_root()
    base = None
    if base_file_present(root, (_BASELINE_REL,)):
        base = set(base_table(root, (_BASELINE_REL,), "COMMIT_BEFORE_ANSWER_BASELINE", absent_as_empty=True))
    added = baseline_additions(set(COMMIT_BEFORE_ANSWER_BASELINE), base)
    assert not added, f"files added to a shrink-only baseline: {sorted(added)}; move them to session_dep instead"


def test_a_baseline_addition_is_reported_and_a_removal_is_not() -> None:
    assert baseline_additions({"a", "b"}, {"a"}) == {"b"}
    assert baseline_additions({"a"}, {"a", "b"}) == set()
    assert baseline_additions({"a"}, None) == set(), "a baseline new at this head starts at its first measurement"


def test_a_baselined_file_that_no_longer_violates_is_stale() -> None:
    assert stale_entries({"a", "b"}, {"a"}) == {"b"}
    assert stale_entries({"a"}, {"a", "c"}) == set()


def test_every_baseline_entry_names_its_blocker() -> None:
    assert all("#" in why for why in COMMIT_BEFORE_ANSWER_BASELINE.values())
    assert all((REPO_ROOT / rel).is_file() for rel in COMMIT_BEFORE_ANSWER_BASELINE)


# ---------------------------------------------------------------------------
# G3: the handlers that open their own session
# ---------------------------------------------------------------------------


def test_a_route_without_a_session_is_reported() -> None:
    found = sessionless_routes([_route(_no_session)])
    assert [name for _, name in found] == ["_no_session"]
    assert not found & set(OWN_SESSION_HANDLERS)


def test_the_routes_without_a_request_session_are_exactly_the_declared_ones(routes: list) -> None:
    found = sessionless_routes(routes)
    assert found == set(OWN_SESSION_HANDLERS), (
        f"undeclared: {sorted(found - set(OWN_SESSION_HANDLERS))}; "
        f"declared but now holding a session: {sorted(set(OWN_SESSION_HANDLERS) - found)}"
    )


def test_every_exemption_carries_a_reason() -> None:
    assert all(reason.strip() for reason in OWN_SESSION_HANDLERS.values())


# ---------------------------------------------------------------------------
# G4: a failed write is never turned into the 2xx the route builds next
# ---------------------------------------------------------------------------

_SWALLOWS_COMMIT = (
    "async def create(session):\n"
    "    try:\n"
    "        await session.commit()\n"
    "    except Exception as exc:\n"
    "        log(exc)\n"
    "        await session.rollback()\n"
    "    return Hire()\n"
)
_FIRES = [
    ("agent_hires_shape", _SWALLOWS_COMMIT),
    (
        "commit_guard_without_rollback",
        "async def f(s):\n    try:\n        await s.commit()\n    except OSError:\n        log()\n    return 1\n",
    ),
    (
        "rollback_then_return",
        "async def f(s):\n    try:\n        await s.flush()\n    except OSError:\n"
        "        await s.rollback()\n        return 1\n",
    ),
]
_QUIET = [
    (
        "rollback_then_raise",
        "async def f(s):\n    try:\n        await s.commit()\n    except OSError:\n"
        "        await s.rollback()\n        raise\n",
    ),
    (
        "rollback_then_no_return_helper",
        "async def refuse(s) -> NoReturn:\n    raise E()\n\n"
        "async def f(s):\n    try:\n        await s.commit()\n    except OSError:\n        await refuse(s)\n",
    ),
    ("no_commit_no_rollback", "async def f():\n    try:\n        run()\n    except OSError:\n        return None\n"),
]


@pytest.mark.parametrize("source", [s for _, s in _FIRES], ids=[i for i, _ in _FIRES])
def test_the_scan_fires_on_a_swallowed_failure(source: str) -> None:
    assert swallowed_failures(source, "x.py")


@pytest.mark.parametrize("source", [s for _, s in _QUIET], ids=[i for i, _ in _QUIET])
def test_the_scan_is_quiet_when_the_failure_surfaces(source: str) -> None:
    assert swallowed_failures(source, "x.py") == []


def test_no_llc_route_module_swallows_a_failed_write() -> None:
    assert swallowed_failures_in_tree() == []


def test_the_decorator_scan_reads_every_router_spelling() -> None:
    source = (
        "@router.post('/a')\nasync def a(): ...\n"
        "@other_router.delete('/b')\nasync def b(): ...\n"
        "@router.get('/c')\nasync def c(): ...\n"
        "def helper(): ...\n"
    )
    assert decorated_write_routes(source, "m.py") == {("m.py", "a"), ("m.py", "b")}


def test_the_guard_scans_the_llc_tree_it_names() -> None:
    assert (LLC_ROOT / "api" / "agent_api.py").is_file(), "llc has moved; update the guard's roots"
