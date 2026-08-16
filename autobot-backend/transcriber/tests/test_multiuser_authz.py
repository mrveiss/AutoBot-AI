# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/transcriber/tests/test_multiuser_authz.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Multi-user authorization regression tests for transcriber rows (#10023).

Pins the #9968 IDOR fix: a second authenticated user must NOT be able to
read, modify, or delete the first user's projects/recordings. All access
goes through transcriber.deps.can_access (#9863 single ownership policy);
if that policy is weakened or a route stops calling it, these tests go red.
"""

import asyncio
import io
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException, Request
from httpx import ASGITransport, AsyncClient

from api.transcripts import _resolve_user_id
from transcriber.database import Database
from transcriber.deps import DEFAULT_USER, can_access, get_db
from transcriber.routes.projects import router as projects_router
from transcriber.routes.recordings import router as recordings_router

USER_HEADER = "x-test-user"


@pytest_asyncio.fixture
async def client(tmp_path):
    """App with both routers and header-driven request.state.user identity."""
    app = FastAPI()
    db = Database(str(tmp_path / "test.db"))
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()

    async def override_db():
        return db

    @app.middleware("http")
    async def set_user(request: Request, call_next):
        uid = request.headers.get(USER_HEADER)
        if uid:
            request.state.user = SimpleNamespace(id=uid)
        return await call_next(request)

    await db.connect()
    app.dependency_overrides[get_db] = override_db
    app.state.transcriber_upload_dir = str(upload_dir)
    app.include_router(projects_router, prefix="/api/transcriber")
    app.include_router(recordings_router, prefix="/api/transcriber")

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
    finally:
        # #13861: `connect()` had no matching `close()`, and aiosqlite runs its
        # connection on a NON-daemon worker thread. Every one of the 8 tests
        # created a fixture, so 8 threads outlived the run and the interpreter
        # could never exit — the suite passed, printed `........ [100%]`, and
        # then hung until CI cancelled the job at 15 minutes. 20 of 20 runs
        # across seven branches ended `cancelled`, never once pass or fail.
        await db.close()


async def _create_project(client, user: str) -> int:
    r = await client.post(
        "/api/transcriber/projects",
        json={"name": f"{user}-project", "description": ""},
        headers={USER_HEADER: user},
    )
    assert r.status_code == 201
    return r.json()["id"]


async def _upload_recording(client, user: str, pid: int) -> int:
    r = await client.post(
        f"/api/transcriber/projects/{pid}/recordings",
        files={"file": ("a.wav", io.BytesIO(b"RIFF" + b"\x00" * 32), "audio/wav")},
        headers={USER_HEADER: user},
    )
    assert r.status_code == 202
    return r.json()["id"]


def test_can_access_policy_unit():
    """can_access: strict ownership — owner yes, everyone else no.

    Cases required by #9968:
    (a) owner == caller → allow
    (b) different real users → deny
    (c) DEFAULT_USER row + DEFAULT_USER caller → allow
    (d) DEFAULT_USER row + real user → DENY  (was the IDOR)
    (e) unowned / empty user_id → deny
    """
    # (a) owner == caller → allow
    assert can_access({"user_id": "alice"}, "alice") is True
    # (b) different real users → deny
    assert can_access({"user_id": "alice"}, "bob") is False
    # (c) DEFAULT_USER caller accesses DEFAULT_USER row → allow
    assert can_access({"user_id": DEFAULT_USER}, DEFAULT_USER) is True
    # (d) IDOR fix: real user must NOT access DEFAULT_USER-owned row
    assert can_access({"user_id": DEFAULT_USER}, "bob") is False
    # (e) unowned (no user_id key) → deny
    assert can_access({}, "bob") is False
    # (e) explicit empty string user_id → deny
    assert can_access({"user_id": ""}, "bob") is False


def test_resolve_user_id_returns_real_identity():
    """_resolve_user_id: returns user_id or username when present."""
    assert _resolve_user_id({"user_id": "alice"}) == "alice"
    assert _resolve_user_id({"username": "bob"}) == "bob"
    # user_id takes precedence over username
    assert _resolve_user_id({"user_id": "alice", "username": "other"}) == "alice"


def test_resolve_user_id_raises_when_no_identity():
    """_resolve_user_id: raises 403 — never silently returns DEFAULT_USER (#9968)."""
    with pytest.raises(HTTPException) as exc_info:
        _resolve_user_id({})
    assert exc_info.value.status_code == 403

    with pytest.raises(HTTPException) as exc_info:
        _resolve_user_id({"user_id": None, "username": None})
    assert exc_info.value.status_code == 403

    with pytest.raises(HTTPException) as exc_info:
        _resolve_user_id({"user_id": "", "username": ""})
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_second_user_cannot_read_first_users_project(client):
    pid = await _create_project(client, "alice")
    r = await client.get(f"/api/transcriber/projects/{pid}", headers={USER_HEADER: "bob"})
    assert r.status_code == 404, "IDOR (#9968): bob read alice's project"
    # Owner still sees it
    r = await client.get(f"/api/transcriber/projects/{pid}", headers={USER_HEADER: "alice"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_second_user_cannot_modify_or_delete_project(client):
    pid = await _create_project(client, "alice")
    r = await client.patch(
        f"/api/transcriber/projects/{pid}",
        json={"name": "hijacked"},
        headers={USER_HEADER: "bob"},
    )
    assert r.status_code == 404, "IDOR (#9968): bob modified alice's project"
    r = await client.delete(f"/api/transcriber/projects/{pid}", headers={USER_HEADER: "bob"})
    assert r.status_code == 404, "IDOR (#9968): bob deleted alice's project"
    # Row untouched
    r = await client.get(f"/api/transcriber/projects/{pid}", headers={USER_HEADER: "alice"})
    assert r.status_code == 200
    assert r.json()["name"] == "alice-project"


@pytest.mark.asyncio
async def test_project_listing_is_scoped_per_user(client):
    pid = await _create_project(client, "alice")
    r = await client.get("/api/transcriber/projects", headers={USER_HEADER: "bob"})
    assert r.status_code == 200
    assert pid not in [p["id"] for p in r.json()], "bob's listing leaked alice's project"


@pytest.mark.asyncio
async def test_second_user_cannot_access_recordings(client):
    pid = await _create_project(client, "alice")
    rid = await _upload_recording(client, "alice", pid)

    r = await client.get(f"/api/transcriber/projects/{pid}/recordings", headers={USER_HEADER: "bob"})
    assert r.status_code == 404, "IDOR (#9968): bob listed alice's recordings"
    r = await client.get(f"/api/transcriber/recordings/{rid}", headers={USER_HEADER: "bob"})
    assert r.status_code == 404, "IDOR (#9968): bob read alice's recording"
    r = await client.delete(f"/api/transcriber/recordings/{rid}", headers={USER_HEADER: "bob"})
    assert r.status_code == 404, "IDOR (#9968): bob deleted alice's recording"
    r = await client.post(
        f"/api/transcriber/projects/{pid}/recordings",
        files={"file": ("b.wav", io.BytesIO(b"RIFF" + b"\x00" * 8), "audio/wav")},
        headers={USER_HEADER: "bob"},
    )
    assert r.status_code == 404, "IDOR (#9968): bob uploaded into alice's project"


@pytest.mark.asyncio
async def test_legacy_default_rows_not_accessible_to_other_users(client):
    """DEFAULT_USER rows are NOT shared across real users (#9968 IDOR fix).

    Pre-auth rows (stamped DEFAULT_USER) are accessible only by the
    DEFAULT_USER caller.  Real authenticated users are denied — the old
    "any caller can read default rows" behaviour was the IDOR.  Cross-user
    reassignment of legacy rows is tracked separately.
    """
    r = await client.post(
        "/api/transcriber/projects", json={"name": "legacy", "description": ""}
    )  # no user header -> DEFAULT_USER
    pid = r.json()["id"]
    # Real user bob is DENIED access to a DEFAULT_USER-owned row
    r = await client.get(f"/api/transcriber/projects/{pid}", headers={USER_HEADER: "bob"})
    assert r.status_code == 404, "IDOR (#9968): real user should not access DEFAULT_USER rows"
    # DEFAULT_USER caller can still access its own rows
    r = await client.get(f"/api/transcriber/projects/{pid}", headers={USER_HEADER: DEFAULT_USER})
    assert r.status_code == 200


class TestTheFixtureDoesNotLeakConnections:
    """#13861: co-located-smoke had never completed — 20 of 20 runs cancelled.

    Not one `success`, not one `failure`, across seven branches over a week.
    The tests all PASSED; the interpreter then hung, because `client` called
    `db.connect()` with no matching `close()` and aiosqlite runs its connection
    on a NON-daemon worker thread. Eight tests, eight fixtures, eight threads
    that outlive the run — so the process could never exit and CI cancelled the
    job at its 15-minute timeout.

    A check that can only ever be cancelled produces no signal in either
    direction: it cannot pass, so it confirms nothing; it cannot fail, so nobody
    investigates. Meanwhile it sits in the PR check list looking like coverage.
    """

    @pytest.mark.asyncio
    async def test_a_closed_database_leaves_no_worker_thread(self, tmp_path):
        """Assert the invariant, not the symptom. A test that merely finishes
        proves nothing here — the old suite finished too, and then hung."""
        import threading

        before = {t.ident for t in threading.enumerate()}

        db = Database(str(tmp_path / "leak.db"))
        await db.connect()
        during = {t.ident for t in threading.enumerate()} - before
        assert during, "aiosqlite should have started a worker thread — otherwise this guards nothing"

        await db.close()

        for _ in range(50):
            if not ({t.ident for t in threading.enumerate()} & during):
                break
            await asyncio.sleep(0.05)
        else:
            pytest.fail(
                "aiosqlite worker thread outlived close() — it is non-daemon, so the "
                "interpreter cannot exit and CI cancels the job with no failure (#13861)"
            )

    @pytest.mark.asyncio
    async def test_close_is_idempotent(self, tmp_path):
        """The fixture closes in a `finally`, so a test that already closed must
        not turn teardown into an error."""
        db = Database(str(tmp_path / "twice.db"))
        await db.connect()
        await db.close()
        await db.close()

    def test_no_fixture_in_this_directory_connects_without_closing(self):
        """Structural, and directory-wide, because the symptom is at INTERPRETER EXIT.

        Deleting a `close()` does not fail a test — it makes the process hang
        after the suite passes, which in CI is another cancelled job with no
        failure. So a guard that only reproduces it is a guard that hangs too;
        this one fails in milliseconds.

        Two earlier versions of this were weaker, and both weaknesses are the
        reason it is written this way:

        It matched attribute names only, so ANY `.close()` on any object in the
        fixture disarmed it — an unrelated `StringIO().close()` made it pass
        while `db` leaked. It now requires the receiver to be the same name the
        `connect()` was called on.

        And it checked only this file, while four siblings in the same directory
        carried the identical leak and hung the interpreter today. They survive
        `ci.yml` only because xdist's execnet workers exit hard; the moment one
        reaches a serial invocation — co-located-smoke is exactly that — #13861
        recurs verbatim. Asserting the invariant over the directory is what
        catches that; asserting the reported instance is what missed it.
        """
        import ast

        offenders: list[str] = []
        directory = Path(__file__).resolve().parent
        for path in sorted(directory.glob("test_*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                    continue
                # `async with aiosqlite.connect(...)` closes on exit — those are
                # correct and must not be flagged, or the guard cries wolf and
                # gets deleted.
                managed = {
                    id(item.context_expr)
                    for inner in ast.walk(node)
                    if isinstance(inner, (ast.With, ast.AsyncWith))
                    for item in inner.items
                }
                opened, closed = set(), set()
                for call in ast.walk(node):
                    if id(call) in managed:
                        continue
                    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)):
                        continue
                    receiver = call.func.value
                    if not isinstance(receiver, ast.Name):
                        continue
                    if call.func.attr == "connect":
                        opened.add(receiver.id)
                    elif call.func.attr == "close":
                        closed.add(receiver.id)
                for name in opened - closed:
                    offenders.append(f"{path.name}::{node.name} opens `{name}` and never closes it")

        assert not offenders, (
            "aiosqlite's worker thread is non-daemon, so an unclosed connection keeps the "
            "interpreter alive after the suite passes and CI cancels the job with no failure "
            "reported (#13861):\n  " + "\n  ".join(offenders)
        )

    def test_the_guard_can_see_the_connections_it_checks(self):
        """Guard the guard: if the fixtures stop calling `.connect()` by that
        name, the check above passes against nothing."""
        import ast

        directory = Path(__file__).resolve().parent
        found = 0
        for path in directory.glob("test_*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "connect":
                    found += 1
        assert found >= 8, f"expected the directory's Database.connect() calls, found {found}"
