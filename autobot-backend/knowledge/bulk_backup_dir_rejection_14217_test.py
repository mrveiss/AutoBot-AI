# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``_get_backup_dir`` must reject a non-path value, not hand it to
``os.makedirs`` (#14217).

``backup_dir`` was returned unvalidated: any truthy value — including an
object whose ``__fspath__``/``str()`` happens to look path-like — went
straight into ``os.makedirs(backup_dir, exist_ok=True)`` at
``knowledge/bulk.py:1448``. ``os.makedirs`` (like ``Path()``) never raises
for such an object; it silently creates whatever directory tree the value
implies.
"""

from unittest.mock import MagicMock

import pytest

from knowledge.bulk import BulkOperationsMixin


class TestGetBackupDirRejectsNonPath:
    """Unit-level: the boundary check inside ``_get_backup_dir`` itself."""

    def test_magicmock_backup_dir_rejected(self):
        """The real reproduction: an object, not a crafted string."""
        mixin = BulkOperationsMixin()
        with pytest.raises(TypeError):
            mixin._get_backup_dir(MagicMock(name="mock.settings.backup_dir"))

    def test_empty_string_backup_dir_rejected(self):
        mixin = BulkOperationsMixin()
        with pytest.raises(ValueError):
            mixin._get_backup_dir("")

    def test_none_backup_dir_still_falls_back_to_default(self):
        """Unchanged behaviour: no backup_dir means the documented default."""
        mixin = BulkOperationsMixin()
        result = mixin._get_backup_dir(None)
        assert result.endswith("backups/knowledge")

    def test_normal_string_backup_dir_still_accepted(self, tmp_path):
        """Unchanged behaviour: a real caller-supplied directory still works."""
        mixin = BulkOperationsMixin()
        result = mixin._get_backup_dir(str(tmp_path / "custom"))
        assert result == str(tmp_path / "custom")


class TestCreateBackupRejectsNonPathBackupDir:
    """Integration: drive the real async entry point end to end."""

    async def test_create_backup_with_magicmock_touches_nothing_on_disk(self, tmp_path, monkeypatch):
        """Nothing is created anywhere, not merely a clean return value.

        Before the fix this reproduced the exact reported artifact: a
        MagicMock repr promoted into a real, nested, creatable directory
        tree under whatever the process CWD happened to be.
        """
        monkeypatch.chdir(tmp_path)
        mixin = BulkOperationsMixin()

        result = await mixin.create_backup(backup_dir=MagicMock(name="mock.settings.backup_dir"))

        assert result["status"] == "error"
        assert list(tmp_path.rglob("*")) == [], "create_backup must not create anything on disk"

    async def test_list_backups_with_magicmock_touches_nothing_on_disk(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        mixin = BulkOperationsMixin()

        result = await mixin.list_backups(backup_dir=MagicMock(name="mock.config_manager.get()"))

        assert result["status"] == "error"
        assert list(tmp_path.rglob("*")) == [], "list_backups must not create anything on disk"
