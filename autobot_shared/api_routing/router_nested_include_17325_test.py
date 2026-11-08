# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A router served only through another module's ``include_router`` (#17325).

``api.chat_sessions`` lost its registry entry when its duplicate mount was
removed; ``api/chat.py`` still serves it via ``router.include_router(sessions_router)``.
``resolve_registry_targets`` read only the registry, so every route the nested
router declares vanished from the route table although the app serves them.
"""

from __future__ import annotations

from pathlib import Path

from autobot_shared.api_routing.router_prefixes import resolve_registry_target_prefixes, resolve_registry_targets

_CHILD = "from fastapi import APIRouter\nrouter = APIRouter(prefix='/sessions')\n"


def _write(root: Path, rel: str, body: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_a_router_included_by_a_registered_module_is_served(tmp_path):
    parent = _write(
        tmp_path,
        "api/chat.py",
        "from fastapi import APIRouter\nrouter = APIRouter(prefix='/v1')\n"
        "from api.chat_sessions import router as sessions_router\n"
        "router.include_router(sessions_router, prefix='/s')\n",
    )
    child = _write(tmp_path, "api/chat_sessions.py", _CHILD)
    targets = resolve_registry_targets(tmp_path, [("api.chat", "/chat")])
    assert targets[parent] == "/chat"
    assert targets[child] == "/chat/v1/s", "parent prefix + include prefix must carry to the nested router"


def test_an_imported_but_unmounted_router_serves_nothing(tmp_path):
    """Contrast: the import alone is not a mount."""
    _write(
        tmp_path,
        "api/chat.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n"
        "from api.chat_sessions import router as sessions_router\n",
    )
    child = _write(tmp_path, "api/chat_sessions.py", _CHILD)
    assert child not in resolve_registry_targets(tmp_path, [("api.chat", "/chat")])


def test_an_include_cycle_terminates(tmp_path):
    _write(tmp_path, "api/a.py", "from api.b import router as b_router\nrouter.include_router(b_router)\n")
    b = _write(tmp_path, "api/b.py", "from api.a import router as a_router\nrouter.include_router(a_router)\n")
    targets = resolve_registry_targets(tmp_path, [("api.a", "/a")])
    assert targets[b] == "/a"
    assert targets[tmp_path / "api" / "a.py"] == "/a", "the cycle must not overwrite the registry prefix"


def test_a_registry_prefix_wins_over_an_included_one(tmp_path):
    _write(tmp_path, "api/chat.py", "from api.x import router as x_router\nrouter.include_router(x_router)\n")
    x = _write(tmp_path, "api/x.py", _CHILD)
    for entries in ([("api.x", "/x"), ("api.chat", "/chat")], [("api.chat", "/chat"), ("api.x", "/x")]):
        assert resolve_registry_targets(tmp_path, entries)[x] == "/x", entries


def test_one_alias_included_at_two_prefixes_is_served_at_both(tmp_path):
    _write(
        tmp_path,
        "api/chat.py",
        "from fastapi import APIRouter\nrouter = APIRouter(prefix='/v1')\n"
        "from api.chat_sessions import router as sessions_router\n"
        "router.include_router(sessions_router, prefix='/a')\n"
        "router.include_router(sessions_router, prefix='/b')\n",
    )
    child = _write(tmp_path, "api/chat_sessions.py", _CHILD)
    prefixes = resolve_registry_target_prefixes(tmp_path, [("api.chat", "/chat")])[child]
    assert prefixes == ["/chat/v1/a", "/chat/v1/b"]
    assert resolve_registry_targets(tmp_path, [("api.chat", "/chat")])[child] == "/chat/v1/a"
