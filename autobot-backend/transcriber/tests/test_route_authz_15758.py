# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The transcriber gates closing #15758, exercised through the routes themselves.

These cover the gaps from the #16259 review:

- ownership on ``ai/ask`` and the ``kb`` routes, which no test covered;
- a real anonymous 401 from each sub-router, with ``authenticate`` left in
  place (every other fixture overrides it);
- the reserved ``"default"`` identity;
- the owner ruling (2026-09-11) that ``PATCH /providers`` is admin-only.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException, Request
from httpx import ASGITransport, AsyncClient

from transcriber.database import Database
from transcriber.deps import DEFAULT_USER, authenticate, get_current_user, get_db, resolve_user_id
from transcriber.routes.ai import router as ai_router
from transcriber.routes.export import router as export_router
from transcriber.routes.kb import router as kb_router
from transcriber.routes.projects import router as projects_router
from transcriber.routes.providers import router as providers_router
from transcriber.routes.recordings import router as recordings_router
from transcriber.routes.transcripts import router as transcripts_router

PREFIX = "/api/transcriber"
USER_HEADER = "x-test-user"
OWNER = "alice"
OTHER = "bob"

_ALL_ROUTERS = (
    ai_router,
    export_router,
    kb_router,
    projects_router,
    providers_router,
    recordings_router,
    transcripts_router,
)


# ---------------------------------------------------------------------------
# Ownership: ai/ask, kb/push and kb/status refuse another user's recording.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def seeded(tmp_path):
    """App whose caller is named by a header. It holds one recording owned by OWNER."""
    app = FastAPI()
    db = Database(str(tmp_path / "test.db"))
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()

    async def override_db():
        return db

    @app.middleware("http")
    async def inject_user(request: Request, call_next):
        uid = request.headers.get(USER_HEADER)
        if uid:
            request.state.user = SimpleNamespace(id=uid)
        return await call_next(request)

    await db.connect()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[authenticate] = lambda: None
    for router in (ai_router, kb_router, recordings_router):
        app.include_router(router, prefix=PREFIX)

    pid = await db.create_project("Owned", "", OWNER)
    fake_file = upload_dir / "sample.wav"
    await asyncio.to_thread(fake_file.write_bytes, b"RIFF" + b"\x00" * 32)
    rid = await db.create_recording(pid, "sample.wav", str(fake_file), OWNER)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c, rid
    finally:
        # #13861: close the aiosqlite connection, or its non-daemon thread keeps a serial run alive.
        await db.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        ("POST", "/ai/ask", {"action": "summarize"}),
        ("POST", "/kb/push", {"collection_id": "c1"}),
        ("GET", "/kb/status", None),
    ],
    ids=["ai-ask", "kb-push", "kb-status"],
)
async def test_another_user_cannot_reach_the_recording(seeded, method, suffix, body):
    client, rid = seeded
    r = await client.request(method, f"{PREFIX}/recordings/{rid}{suffix}", json=body, headers={USER_HEADER: OTHER})
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_the_owner_reaches_kb_status(seeded):
    """The contrast case: the owner passes the same check, so the 404 above is the ownership refusal."""
    client, rid = seeded
    r = await client.get(f"{PREFIX}/recordings/{rid}/kb/status", headers={USER_HEADER: OWNER})
    assert r.status_code == 200, r.text
    assert r.json()["pushed"] is False


# ---------------------------------------------------------------------------
# Anonymous 401 through the real authenticate, one route per sub-router.
# ---------------------------------------------------------------------------


def _refuse_login():
    raise HTTPException(status_code=401, detail="Authentication required")


def _unauthenticated_app(current_user=None) -> FastAPI:
    """Every sub-router, with ``authenticate`` REAL. Only the credential check it wraps is replaced."""
    app = FastAPI()
    for router in _ALL_ROUTERS:
        app.include_router(router, prefix=PREFIX)
    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[get_current_user] = current_user or _refuse_login
    return app


_ONE_ROUTE_PER_SUB_ROUTER = [
    ("ai", "POST", "/recordings/1/ai/ask", {"action": "summarize"}),
    ("export", "POST", "/recordings/1/export", {"format": "srt"}),
    ("kb", "GET", "/recordings/1/kb/status", None),
    ("projects", "GET", "/projects", None),
    ("providers", "GET", "/providers", None),
    ("recordings", "GET", "/projects/1/recordings", None),
    ("transcripts", "GET", "/recordings/1/transcript", None),
]


def test_the_route_table_covers_every_sub_router():
    """Keeps the 401 test below from going vacuous when a sub-router is added."""
    assert len(_ONE_ROUTE_PER_SUB_ROUTER) == len(_ALL_ROUTERS)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module", "method", "path", "body"), _ONE_ROUTE_PER_SUB_ROUTER, ids=[r[0] for r in _ONE_ROUTE_PER_SUB_ROUTER]
)
async def test_an_anonymous_caller_gets_401_from_every_sub_router(module, method, path, body):
    app = _unauthenticated_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.request(method, f"{PREFIX}{path}", json=body)
    assert r.status_code == 401, f"{module}: {r.status_code} {r.text}"


@pytest.mark.asyncio
async def test_a_signed_in_caller_passes_the_same_gate():
    """The contrast case: the same app with a signed-in caller reaches the handler."""
    app = _unauthenticated_app(lambda: {"user_id": OWNER, "role": "user"})
    with (
        patch("transcriber.routes.providers.list_available_providers", return_value=[]),
        patch("transcriber.routes.providers.get_active_provider_id", return_value=None),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get(f"{PREFIX}/providers")
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# PATCH /providers is admin-only (owner ruling, 2026-09-11).
# ---------------------------------------------------------------------------


async def _patch_providers_as(role: str):
    app = _unauthenticated_app(lambda: {"user_id": "someone", "role": role})
    with (
        patch("transcriber.routes.providers.set_active_provider") as set_provider,
        patch("transcriber.routes.providers.list_available_providers", return_value=[]),
        patch("transcriber.routes.providers.get_active_provider_id", return_value=None),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.patch(f"{PREFIX}/providers", json={"provider": None})
    return r, set_provider


@pytest.mark.asyncio
async def test_a_non_admin_cannot_switch_the_provider():
    """It would route every user's audio to another cloud provider."""
    r, set_provider = await _patch_providers_as("user")
    assert r.status_code == 403, r.text
    set_provider.assert_not_called()


@pytest.mark.asyncio
async def test_an_admin_can_switch_the_provider():
    r, set_provider = await _patch_providers_as("admin")
    assert r.status_code == 200, r.text
    set_provider.assert_called_once_with(None)


# ---------------------------------------------------------------------------
# "default" is reserved for pre-#15758 rows.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("principal", [{"user_id": DEFAULT_USER}, {"username": DEFAULT_USER}])
def test_no_principal_can_resolve_to_the_legacy_owner(principal):
    """Otherwise a user named "default" would own every pre-#15758 row."""
    with pytest.raises(HTTPException) as refused:
        resolve_user_id(principal)
    assert refused.value.status_code == 403


def test_an_ordinary_principal_still_resolves():
    assert resolve_user_id({"user_id": OWNER}) == OWNER
    assert resolve_user_id({"username": "carol"}) == "carol"
