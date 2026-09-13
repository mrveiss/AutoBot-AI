#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Chat-knowledge contexts can now be deleted, and orphans swept (#16490).

Before this module, ``api/chat_knowledge.py`` had no DELETE route at all: a
context, once created, lived forever. These tests cover the three ACs
``DELETE /context/{chat_id}`` exists for -- the owner (or an admin) deletes
successfully with every dependent record gone, a non-owner is refused, and an
unknown ``chat_id`` is a clean 404 -- plus the admin-only orphan sweep.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.chat_knowledge_delete import delete_chat_knowledge_context, router
from api.chat_knowledge_manager import MANAGER_STATE_KEY
from auth_middleware import check_admin_permission

API_PREFIX = "/api/chat-knowledge"
CHAT_ID = "chat-16490"


def _manager(**overrides) -> SimpleNamespace:
    """A bare stand-in for ChatKnowledgeManager carrying only the attributes
    delete_chat_knowledge_context and the orphan sweep actually touch."""
    defaults = {
        "chat_contexts": {},
        "file_associations": {},
        "pending_decisions": {},
        "storage_dir": "/tmp/unused-chat-knowledge-storage",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _app(manager: SimpleNamespace | None) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix=API_PREFIX)
    if manager is not None:
        setattr(app.state, MANAGER_STATE_KEY, manager)
    return app


class _StubChatHistoryManager:
    """Reports a fixed set of chat_ids as the only ones that "exist"."""

    def __init__(self, existing_ids):
        self._existing_ids = existing_ids

    async def list_sessions_fast(self):
        return [{"id": chat_id} for chat_id in self._existing_ids]


class TestDeleteContextOwnership:
    """AC: owner/admin deletes with dependents gone; non-owner 403; unknown 404."""

    def test_owner_deletes_and_every_dependent_record_is_gone(self, tmp_path):
        owned_file = tmp_path / f"{CHAT_ID}_notes.txt"
        owned_file.write_text("hello", encoding="utf-8")
        manager = _manager(
            chat_contexts={CHAT_ID: object()},
            file_associations={CHAT_ID: [SimpleNamespace(file_path=str(owned_file))]},
            pending_decisions={CHAT_ID: [{"id": "p1"}]},
            storage_dir=str(tmp_path),
        )
        client = TestClient(_app(manager))
        ownership = AsyncMock(return_value={"authorized": True, "reason": "owner_match"})

        with patch("api.chat.validate_chat_ownership", new=ownership):
            response = client.delete(f"{API_PREFIX}/context/{CHAT_ID}")

        assert response.status_code == 200, response.text
        body = response.json()["data"]
        assert body["deleted"] is True
        assert body["file_associations_removed"] == 1
        assert body["authorized_via"] == "owner_match"
        assert CHAT_ID not in manager.chat_contexts
        assert CHAT_ID not in manager.file_associations
        assert CHAT_ID not in manager.pending_decisions
        assert not owned_file.exists(), "the file this manager itself wrote must be removed too"
        assert ownership.await_args.args[0] == CHAT_ID, "ownership must be checked against the path's chat_id"

    def test_a_non_owner_gets_403_and_nothing_is_deleted(self):
        manager = _manager(chat_contexts={CHAT_ID: object()})
        client = TestClient(_app(manager))

        async def _refused(*_args, **_kwargs):
            raise HTTPException(status_code=403, detail="not your context")

        with patch("api.chat.validate_chat_ownership", new=_refused):
            response = client.delete(f"{API_PREFIX}/context/{CHAT_ID}")

        assert response.status_code == 403
        assert CHAT_ID in manager.chat_contexts, "a refused caller must not have deleted anything"

    def test_an_unknown_chat_id_is_a_404(self):
        client = TestClient(_app(_manager()))

        response = client.delete(f"{API_PREFIX}/context/does-not-exist")

        assert response.status_code == 404

    def test_no_manager_ever_built_is_also_a_404(self):
        """peek_chat_knowledge_manager returning None must not construct one."""
        client = TestClient(_app(manager=None))

        response = client.delete(f"{API_PREFIX}/context/{CHAT_ID}")

        assert response.status_code == 404


class TestDeleteChatKnowledgeContextHelper:
    """Direct tests of the manager-level helper, independent of HTTP/auth."""

    @pytest.mark.asyncio
    async def test_returns_none_when_chat_id_is_unknown(self):
        assert await delete_chat_knowledge_context(_manager(), "missing") is None

    @pytest.mark.asyncio
    async def test_removes_context_file_associations_and_pending_decisions(self, tmp_path):
        owned = tmp_path / f"{CHAT_ID}_a.txt"
        await asyncio.to_thread(owned.write_text, "x", encoding="utf-8")
        manager = _manager(
            chat_contexts={CHAT_ID: object()},
            file_associations={CHAT_ID: [SimpleNamespace(file_path=str(owned))]},
            pending_decisions={CHAT_ID: [{"id": "p1"}]},
            storage_dir=str(tmp_path),
        )

        removed = await delete_chat_knowledge_context(manager, CHAT_ID)

        assert removed == 1
        assert CHAT_ID not in manager.chat_contexts
        assert CHAT_ID not in manager.pending_decisions
        assert not owned.exists()

    @pytest.mark.asyncio
    async def test_a_file_outside_storage_dir_survives(self, tmp_path):
        """associate_file_with_chat can point at a file this manager never wrote."""
        outside = tmp_path / "other_subsystem" / "keep.txt"
        outside.parent.mkdir()
        await asyncio.to_thread(outside.write_text, "keep me", encoding="utf-8")
        storage_dir = tmp_path / "chat_knowledge_storage"
        storage_dir.mkdir()
        manager = _manager(
            chat_contexts={CHAT_ID: object()},
            file_associations={CHAT_ID: [SimpleNamespace(file_path=str(outside))]},
            storage_dir=str(storage_dir),
        )

        await delete_chat_knowledge_context(manager, CHAT_ID)

        assert outside.exists(), "a file outside the manager's own storage_dir must survive"


class TestOrphanSweep:
    """AC: contexts whose chat_id matches no chat are found and cleaned."""

    def _app_as_admin(self, manager, existing_ids):
        app = _app(manager)
        setattr(app.state, "chat_history_manager", _StubChatHistoryManager(existing_ids))
        app.dependency_overrides[check_admin_permission] = lambda: True
        return app

    def test_find_lists_only_contexts_with_no_matching_chat(self):
        manager = _manager(chat_contexts={"kept": object(), "orphan": object()})
        client = TestClient(self._app_as_admin(manager, existing_ids=["kept"]))

        response = client.get(f"{API_PREFIX}/context-orphans")

        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["orphaned_count"] == 1
        assert data["orphaned_chat_ids"] == ["orphan"]
        assert "kept" in manager.chat_contexts, "listing must never delete anything"

    def test_cleanup_dry_run_reports_without_deleting(self):
        manager = _manager(chat_contexts={"orphan": object()})
        client = TestClient(self._app_as_admin(manager, existing_ids=[]))

        response = client.delete(f"{API_PREFIX}/context-orphans")

        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["dry_run"] is True
        assert data["deleted_count"] == 0
        assert "orphan" in manager.chat_contexts

    def test_cleanup_without_dry_run_deletes_the_orphans(self):
        manager = _manager(chat_contexts={"orphan": object()})
        client = TestClient(self._app_as_admin(manager, existing_ids=[]))

        response = client.delete(f"{API_PREFIX}/context-orphans", params={"dry_run": "false"})

        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["dry_run"] is False
        assert data["deleted_count"] == 1
        assert "orphan" not in manager.chat_contexts

    def test_a_non_admin_gets_403_on_both_routes(self):
        manager = _manager(chat_contexts={"orphan": object()})
        app = self._app_as_admin(manager, existing_ids=[])

        def _raise_403():
            raise HTTPException(status_code=403, detail="admin required")

        app.dependency_overrides[check_admin_permission] = _raise_403
        client = TestClient(app)

        assert client.get(f"{API_PREFIX}/context-orphans").status_code == 403
        assert client.delete(f"{API_PREFIX}/context-orphans").status_code == 403
        assert "orphan" in manager.chat_contexts

    def test_no_manager_ever_built_reports_zero_orphans(self):
        client = TestClient(self._app_as_admin(None, existing_ids=[]))

        response = client.get(f"{API_PREFIX}/context-orphans")

        assert response.status_code == 200, response.text
        assert response.json()["data"] == {"orphaned_count": 0, "orphaned_chat_ids": []}
