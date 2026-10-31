# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A non-admin user may upload to a conversation they own; nothing else on the router opens (#20133).

Maintainer decision 2026-10-31. The upload route is gated by the ONE session-ownership dependency
(``validate_session_ownership``, STRICT posture, called from ``_authorize_file_operation``), not by
``check_admin_permission``. Every other route on the router stays admin-only.

Under pytest ``auth_middleware`` is a stub, so these tests execute a FRESH copy of the route module
with the REAL gate bound. The role grant is the REAL ``SecurityLayer.check_permission`` (through the real
``AuthenticationMiddleware.check_file_permissions``): only the identity it reads, the owner store and the
file manager are faked. ``user`` lacks ``files.upload`` there, which is why ownership has to stand in.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, create_autospec

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from autobot_shared.api_routing.router_routes import effective_routes
from conversation_file_manager import ConversationFileManager
from security_layer import SecurityLayer
from testkit.canonical_gate import install_canonical_resolver
from tests.conftest import load_real_auth_middleware

_MODULE = Path(__file__).parent / "conversation_files.py"
_UPLOAD = "/api/conversation/{session_id}/upload"
_ALICE = {"username": "alice", "role": "user"}
_BOB = {"username": "bob", "role": "user"}
_READONLY = {"username": "alice", "role": "readonly"}
_EDITOR = {"username": "alice", "role": "editor"}
_ADMIN = {"username": "root", "role": "admin"}
_FILES = {"file": ("notes.txt", b"hello", "text/plain")}


def _file_info(session_id: str, user_id: str) -> dict:
    return {
        "file_id": "f1",
        "filename": "notes.txt",
        "original_filename": "notes.txt",
        "size": 5,
        "mime_type": "text/plain",
        "session_id": session_id,
        "uploaded_at": datetime(2026, 10, 31, tzinfo=timezone.utc),
        "uploaded_by": user_id,
        "file_path": "/x/notes.txt",
        "extension": ".txt",
    }


@pytest.fixture
def world(monkeypatch):
    """The fresh route module under the real gate; ``world.user``/``world.owner`` steer the fakes."""
    state = SimpleNamespace(user=None, owner=None, owner_error=None, exists=True)
    real = load_real_auth_middleware()

    middleware = MagicMock()
    middleware.get_user_from_request = lambda _request: state.user
    middleware.security_layer = SecurityLayer()  # the REAL role grants
    middleware._log_file_access_denied = lambda *a, **k: None
    middleware._log_file_access_granted = lambda *a, **k: None

    async def _check_file_permissions(request, operation):
        return await real.AuthenticationMiddleware.check_file_permissions(middleware, request, operation)

    middleware.check_file_permissions = _check_file_permissions
    middleware._extract_user_from_run_jwt = AsyncMock(return_value=None)
    middleware._extract_user_from_device_jwt = AsyncMock(return_value=None)
    monkeypatch.setattr(real, "get_auth_middleware", lambda: middleware)
    monkeypatch.setattr(real, "verify_internal_api_key", lambda _provided: False)
    monkeypatch.setitem(sys.modules, "auth_middleware", real)
    install_canonical_resolver(monkeypatch, "security.session_posture.resolve_human_user", middleware)

    async def _owner(_session_id):
        if state.owner_error:
            raise state.owner_error
        return state.owner

    history = SimpleNamespace(get_session_owner=_owner)
    monkeypatch.setattr("utils.chat_utils.get_chat_history_manager", lambda _request: history)
    monkeypatch.setattr("chat_history.session_file.session_file_exists", AsyncMock(side_effect=lambda *_: state.exists))

    spec = importlib.util.spec_from_file_location("_fresh_20133_conversation_files", _MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    manager = create_autospec(ConversationFileManager, instance=True)  # a method it lacks would fail here (#20225)
    manager.upload_file.side_effect = lambda **kw: _file_info(kw["session_id"], kw["user_id"])
    manager.list_files.return_value = {"files": [], "total_files": 0, "total_size": 0}
    app = FastAPI()
    app.include_router(module.router, prefix="/api")
    app.state.conversation_file_manager = manager
    app.state.security_layer = MagicMock()
    state.app = app
    state.client = TestClient(app, raise_server_exceptions=False)
    state.manager = manager
    state.module = module
    state.security_layer = middleware.security_layer
    return state


def _upload(world, session_id="s-1"):
    return world.client.post(f"/api/conversation/{session_id}/upload", files=_FILES)


def test_the_real_role_grants_this_decision_rests_on(world):
    """If ``user`` ever gains ``files.upload`` the ownership stand-in is redundant, not wrong; if
    ``readonly`` ever gains it, the readonly refusal below no longer tests the stand-in."""
    layer = world.security_layer
    grants = {role: layer.check_permission(role, "files.upload") for role in ("user", "readonly", "editor", "admin")}
    assert grants == {"user": False, "readonly": False, "editor": True, "admin": True}


def test_the_owner_may_upload_to_their_own_conversation(world):
    world.user, world.owner = dict(_ALICE), "alice"
    response = _upload(world)
    assert response.status_code == 200, response.text
    kwargs = world.manager.upload_file.await_args.kwargs
    assert (kwargs["session_id"], kwargs["user_id"], kwargs["filename"]) == ("s-1", "alice", "notes.txt")


def test_the_owners_upload_response_carries_no_server_path(world):
    world.user, world.owner = dict(_ALICE), "alice"
    response = _upload(world)
    assert response.status_code == 200, response.text
    info = response.json()["file_info"]
    assert "file_path" not in info
    assert "/x/notes.txt" not in response.text


def test_a_readonly_owner_is_refused(world):
    world.user, world.owner = dict(_READONLY), "alice"
    assert _upload(world).status_code == 403
    world.manager.upload_file.assert_not_awaited()


def test_an_editor_who_holds_the_grant_still_needs_to_own_the_conversation(world):
    world.user, world.owner = dict(_EDITOR), "alice"
    assert _upload(world).status_code == 200
    world.user = {"username": "eve", "role": "editor"}
    assert _upload(world).status_code == 403


def test_a_non_owner_is_refused_and_nothing_is_stored(world):
    world.user, world.owner = dict(_BOB), "alice"
    assert _upload(world).status_code == 403
    world.manager.upload_file.assert_not_awaited()


def test_an_admin_may_upload_to_any_conversation(world):
    world.user, world.owner = dict(_ADMIN), "alice"
    assert _upload(world).status_code == 200
    world.manager.upload_file.assert_awaited_once()


def test_an_unauthenticated_request_is_401(world):
    world.user, world.owner = None, "alice"
    assert _upload(world).status_code == 401
    world.manager.upload_file.assert_not_awaited()


def test_an_unknown_conversation_is_404_for_a_non_admin_and_nothing_is_created(world):
    world.user, world.owner, world.exists = dict(_ALICE), None, False
    assert _upload(world, "never-created").status_code == 404
    world.manager.upload_file.assert_not_awaited()


def test_an_unowned_existing_conversation_is_404_for_a_non_admin(world):
    world.user, world.owner, world.exists = dict(_ALICE), None, True
    assert _upload(world).status_code == 404
    world.manager.upload_file.assert_not_awaited()


def test_an_owner_lookup_failure_fails_closed(world):
    world.user, world.owner_error = dict(_ALICE), RuntimeError("store down")
    assert _upload(world).status_code == 403
    world.manager.upload_file.assert_not_awaited()


def test_the_filename_policy_is_unchanged_for_the_owner(world):
    world.user, world.owner = dict(_ALICE), "alice"
    response = world.client.post("/api/conversation/s-1/upload", files={"file": ("../evil.txt", b"x", "text/plain")})
    assert response.status_code == 400
    world.manager.upload_file.assert_not_awaited()


#: The owner's file panel (#20195) joined the upload on the ownership gate; its rules are pinned in
#: ``conversation_files_owner_routes_20195_test.py``.
_OWNER_ROUTE_SUFFIXES = ("/upload", "/list", "/download/{file_id}", "/preview/{file_id}", "/files/{file_id}")


def _other_routes(world):
    routes = [r for r in effective_routes(world.module.router) if not r.path.endswith(_OWNER_ROUTE_SUFFIXES)]
    assert len(routes) == 10, [(sorted(r.methods), r.path) for r in routes]
    return routes


def test_every_other_route_stays_admin_only_for_the_owner(world):
    """Past the owner routes (upload, list, download, preview, delete) the owner still gets 403."""
    world.user, world.owner = dict(_ALICE), "alice"
    for route in _other_routes(world):
        path = "/api" + route.path.replace("{session_id}", "s-1").replace("{file_id}", "f1")
        for method in route.methods - {"HEAD", "OPTIONS"}:
            response = world.client.request(method, path)
            assert response.status_code == 403, (method, route.path, response.status_code)
    world.manager.list_files.assert_not_awaited()
    world.manager.upload_file.assert_not_awaited()


def test_an_admin_is_still_admitted_to_the_list_route(world):
    world.user, world.owner = dict(_ADMIN), "alice"
    assert world.client.get("/api/conversation/s-1/list").status_code == 200
