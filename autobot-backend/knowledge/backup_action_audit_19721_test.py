# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#19721: deleting or restoring a backup needs a committed audit entry first, naming the person."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

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


async def test_delete_audits_the_person_first_and_returns_the_bare_filename(kb: _KB, tmp_path: Path) -> None:
    with patch.object(backup_audit, "audit_log", AsyncMock(return_value=True)) as audit:
        result = await kb.delete_backup(_NAME, audit_actor="alice")
    assert result == {"status": "success", "deleted_file": _NAME} and _NAME not in os.listdir(tmp_path)
    audit.assert_awaited_once_with("knowledge.backup.delete", user_id="alice", resource=_NAME, durable=True)


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
    audit.assert_awaited_once_with("knowledge.backup.restore", user_id="alice", resource=_NAME, durable=True)


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
    assert (await kb.delete_backup(partial.name))["status"] == "error"


@pytest.mark.parametrize("name", [f"{_NAME}.partial", "../x.json", "a\\b.json", "/abs/x.json", "a\x00b.json"])
def test_the_request_refuses_anything_but_a_filename(name: str) -> None:
    with pytest.raises(ValidationError):
        DeleteBackupRequest(backup_file=name)


def test_the_request_takes_a_filename() -> None:
    assert DeleteBackupRequest(backup_file=_NAME).backup_file == _NAME
