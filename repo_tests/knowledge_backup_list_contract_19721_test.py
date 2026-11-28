# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#19721: the UI reads the identifier the backup list actually returns, and sends it back."""

from __future__ import annotations

import re

from repo_tests._paths import repo_root

_BULK = "autobot-backend/knowledge/bulk.py"
_COMPOSABLE = "autobot-frontend/src/composables/knowledge/useKnowledgeBackup.ts"
_VIEW = "autobot-frontend/src/components/knowledge/BackupManager.vue"


def _read(rel: str) -> str:
    return (repo_root() / rel).read_text(encoding="utf-8")


def test_the_list_returns_a_filename_and_no_name() -> None:
    scan = _read(_BULK).split("def _scan_backup_files", 1)[1].split("return backups", 1)[0]
    assert '"filename": filename' in scan and '"name"' not in scan


def test_the_composable_maps_filename_to_the_ui_s_name() -> None:
    assert "data.backups.map(({ filename, ...rest }) => ({ name: filename, ...rest }))" in _read(_COMPOSABLE)


def test_restore_and_delete_send_that_name() -> None:
    assert len(re.findall(r"backup_file: backupName", _read(_COMPOSABLE))) >= 2
    view = _read(_VIEW)
    assert "restoreBackup(backup.name)" in view and "deleteBackup(backup.name)" in view
