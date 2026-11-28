# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#19721: deleting or restoring a backup needs a committed audit entry first, naming the person."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from pydantic import ValidationError

from api.schemas_knowledge import DeleteBackupRequest
from knowledge import backup_audit
from knowledge.bulk import BulkOperationsMixin

_NAME = "kb_backup_1.json"


class _KB(BulkOperationsMixin):
    def __init__(self, root: Path) -> None:
        self.root = root

    def _get_backup_dir(self, backup_dir):
        return str(self.root)

    async def _restore_facts_from_backup(self, *_args):
        return {"restored": 0}

    def _build_restore_response(self, _data, results):
        return {"status": "success", **results}


@pytest.fixture
def kb(tmp_path: Path) -> _KB:
    (tmp_path / _NAME).write_text(json.dumps({"version": "1.0", "facts": []}), encoding="utf-8")
    return _KB(tmp_path)


def _intent(verb: str):
    return call(f"knowledge.backup.{verb}", user_id="alice", resource=_NAME, durable=True, details={"phase": "intent"})


def _ended(verb: str, result: str):
    details = {"phase": "completion"}
    return call(f"knowledge.backup.{verb}", result, user_id="alice", resource=_NAME, durable=True, details=details)


async def test_delete_audits_the_person_first_and_returns_the_bare_filename(kb: _KB, tmp_path: Path) -> None:
    with patch.object(backup_audit, "audit_log", AsyncMock(return_value=True)) as audit:
        result = await kb.delete_backup(_NAME, audit_actor="alice")
    assert result == {"status": "success", "deleted_file": _NAME} and _NAME not in os.listdir(tmp_path)
    assert audit.await_args_list == [_intent("delete"), _ended("delete", "success")]


async def test_no_audit_entry_means_no_deletion(kb: _KB, tmp_path: Path) -> None:
    with patch.object(backup_audit, "audit_log", AsyncMock(return_value=False)):
        result = await kb.delete_backup(_NAME, audit_actor="alice")
    assert result["status"] == "error" and _NAME in os.listdir(tmp_path)


async def test_a_real_restore_is_audited_and_a_dry_run_is_not(kb: _KB) -> None:
    with (
        patch.object(backup_audit, "audit_log", AsyncMock(return_value=True)) as audit,
        patch.object(kb, "_validate_backup_data", return_value=None),
        patch.object(kb, "_build_dry_run_response", return_value={"status": "dry"}),
    ):
        assert (await kb.restore_backup(_NAME, dry_run=True, audit_actor="alice"))["status"] == "dry"
        audit.assert_not_awaited()
        await kb.restore_backup(_NAME, dry_run=False, audit_actor="alice")
    assert audit.await_args_list == [_intent("restore"), _ended("restore", "success")]


async def test_no_audit_entry_means_no_restore(kb: _KB) -> None:
    with (
        patch.object(backup_audit, "audit_log", AsyncMock(return_value=False)),
        patch.object(kb, "_validate_backup_data", return_value=None),
        patch.object(kb, "_restore_facts_from_backup", AsyncMock()) as restore,
    ):
        result = await kb.restore_backup(_NAME, dry_run=False, audit_actor="alice")
    assert result["status"] == "error"
    restore.assert_not_awaited()


@pytest.fixture
def partial(tmp_path: Path) -> Path:
    path = tmp_path / f"{_NAME}.partial"
    path.write_text("{", encoding="utf-8")
    return path


async def test_a_file_being_written_cannot_be_deleted(kb: _KB, partial: Path) -> None:
    with patch.object(backup_audit, "audit_log", AsyncMock(return_value=True)):  # only the name check can refuse
        assert (await kb.delete_backup(partial.name))["status"] == "error"
    assert partial.name in os.listdir(partial.parent)


@pytest.fixture
def linked(tmp_path: Path) -> Path:
    """A valid backup name that is a symlink to another valid backup in the same directory."""
    other = tmp_path / "kb_backup_2.json"
    other.write_text("{}", encoding="utf-8")
    link = tmp_path / "kb_backup_3.json"
    link.symlink_to(other)
    return link


async def test_a_symlink_is_refused_even_pointing_inside_the_directory(kb: _KB, linked: Path) -> None:
    with patch.object(backup_audit, "audit_log", AsyncMock(return_value=True)) as audit:
        assert (await kb.delete_backup(linked.name, audit_actor="alice"))["status"] == "error"
    audit.assert_not_awaited()
    assert {linked.name, "kb_backup_2.json"} <= set(os.listdir(linked.parent))


async def test_a_delete_that_fails_is_recorded_as_failed(kb: _KB) -> None:
    with (
        patch.object(backup_audit, "audit_log", AsyncMock(return_value=True)) as audit,
        patch("knowledge.bulk.os.remove", side_effect=OSError("busy")),
    ):
        assert (await kb.delete_backup(_NAME, audit_actor="alice"))["status"] == "error"
    assert audit.await_args_list == [_intent("delete"), _ended("delete", "failed")]


@pytest.mark.parametrize(
    "restore",
    [AsyncMock(return_value={"errors": 2}), AsyncMock(side_effect=RuntimeError("boom"))],
    ids=["some-facts-failed", "raised"],
)
async def test_a_restore_that_fails_is_recorded_as_failed(kb: _KB, restore: AsyncMock) -> None:
    with (
        patch.object(backup_audit, "audit_log", AsyncMock(return_value=True)) as audit,
        patch.object(kb, "_validate_backup_data", return_value=None),
        patch.object(kb, "_restore_facts_from_backup", restore),
    ):
        await kb.restore_backup(_NAME, dry_run=False, audit_actor="alice")
    assert audit.await_args_list == [_intent("restore"), _ended("restore", "failed")]


@pytest.mark.parametrize("name", [f"{_NAME}.partial", "../x.json", "a\\b.json", "/abs/x.json", "a\x00b.json"])
def test_the_request_refuses_anything_but_a_filename(name: str) -> None:
    with pytest.raises(ValidationError):
        DeleteBackupRequest(backup_file=name)


def test_the_request_takes_a_filename() -> None:
    assert DeleteBackupRequest(backup_file=_NAME).backup_file == _NAME


@pytest.mark.parametrize("user", [None, {"username": "ana"}])
async def test_the_delete_route_names_the_person_and_refuses_the_service_key(user) -> None:
    from fastapi import HTTPException

    from api import knowledge_maintenance as routes

    kb = MagicMock(delete_backup=AsyncMock(return_value={"status": "success"}))
    body = DeleteBackupRequest(backup_file=_NAME)
    with (
        patch.object(routes, "get_or_create_knowledge_base", AsyncMock(return_value=kb)),
        patch("api.quarantine_read_audit.resolve_human_user", AsyncMock(return_value=user)),
    ):
        if user is None:
            with pytest.raises(HTTPException) as refused:
                await routes.delete_backup(admin_check=True, request=body, req=MagicMock())
            assert refused.value.status_code == 403
            kb.delete_backup.assert_not_awaited()
        else:
            await routes.delete_backup(admin_check=True, request=body, req=MagicMock())
            assert kb.delete_backup.await_args.kwargs["audit_actor"] == "ana"


@pytest.mark.parametrize("dry_run, refused", [(True, False), (False, True)])
async def test_the_service_key_can_only_validate_a_restore(dry_run: bool, refused: bool) -> None:
    from fastapi import HTTPException

    from api import knowledge_maintenance as routes
    from api.schemas_knowledge import RestoreRequest

    kb = MagicMock(restore_backup=AsyncMock(return_value={"status": "success"}))
    body = RestoreRequest(backup_file=_NAME, dry_run=dry_run)
    with (
        patch.object(routes, "get_or_create_knowledge_base", AsyncMock(return_value=kb)),
        patch("api.quarantine_read_audit.resolve_human_user", AsyncMock(return_value=None)),
    ):
        if refused:
            with pytest.raises(HTTPException):
                await routes.restore_backup(admin_check=True, request=body, req=MagicMock())
            kb.restore_backup.assert_not_awaited()
        else:
            await routes.restore_backup(admin_check=True, request=body, req=MagicMock())
            kb.restore_backup.assert_awaited_once()
