# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for GH#8995 data-hygiene retention tasks.

Covers:
- Purge deletes only items older than the retention period
- No-op when period is 0 (disabled)
- keep_forever flag exempts chat sessions from purge
- Idempotent re-run (already-deleted keys are silently skipped)
- audit_emit called once per actual deletion
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ts(days_ago: float) -> str:
    """Return an ISO timestamp string `days_ago` days in the past."""
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.isoformat()


def _session_json(days_ago: float, keep_forever: bool = False) -> bytes:
    """Return a serialised session blob for a session created `days_ago` days ago."""
    data = {
        "id": f"chat-session-{days_ago}",
        "createdAt": _ts(days_ago),
        "keep_forever": keep_forever,
    }
    return json.dumps(data).encode()


# ---------------------------------------------------------------------------
# _is_keep_forever / _parse_created_at helpers
# ---------------------------------------------------------------------------


class TestParseHelpers:
    def test_is_keep_forever_true(self):
        from tasks.chat_retention import _is_keep_forever

        raw = json.dumps({"keep_forever": True}).encode()
        assert _is_keep_forever(raw) is True

    def test_is_keep_forever_false(self):
        from tasks.chat_retention import _is_keep_forever

        raw = json.dumps({"keep_forever": False}).encode()
        assert _is_keep_forever(raw) is False

    def test_is_keep_forever_missing_key(self):
        from tasks.chat_retention import _is_keep_forever

        raw = json.dumps({"id": "abc"}).encode()
        assert _is_keep_forever(raw) is False

    def test_is_keep_forever_camelcase(self):
        from tasks.chat_retention import _is_keep_forever

        raw = json.dumps({"keepForever": True}).encode()
        assert _is_keep_forever(raw) is True

    def test_parse_created_at_iso(self):
        from tasks.chat_retention import _parse_created_at

        ts = _ts(10)
        raw = json.dumps({"createdAt": ts}).encode()
        result = _parse_created_at(raw)
        assert result is not None
        assert result.tzinfo is not None
        assert abs((datetime.now(timezone.utc) - result).days - 10) <= 1

    def test_parse_created_at_missing(self):
        from tasks.chat_retention import _parse_created_at

        raw = json.dumps({"id": "abc"}).encode()
        assert _parse_created_at(raw) is None

    def test_parse_created_at_malformed(self):
        from tasks.chat_retention import _parse_created_at

        raw = json.dumps({"createdAt": "not-a-date"}).encode()
        assert _parse_created_at(raw) is None


# ---------------------------------------------------------------------------
# chat retention — _async_cleanup_expired_chats
# ---------------------------------------------------------------------------


class TestChatRetention:
    @pytest.mark.asyncio
    async def test_no_op_when_disabled(self):
        """retention_days=0 → immediate return, Redis not touched."""
        from tasks.chat_retention import _async_cleanup_expired_chats

        with patch("tasks.chat_retention.get_redis_client") as mock_redis:
            result = await _async_cleanup_expired_chats(retention_days=0)

        mock_redis.assert_not_called()
        assert result["deleted_sessions"] == 0
        assert result["deleted_conversations"] == 0

    @pytest.mark.asyncio
    async def test_deletes_old_session(self):
        """Sessions older than retention_days are deleted with audit emit."""
        from tasks.chat_retention import _async_cleanup_expired_chats

        old_key = b"chat:session:old"
        old_blob = _session_json(days_ago=91)

        redis = MagicMock()
        redis.zremrangebyscore.return_value = 0
        # scan: first call returns the old session key, second ends iteration
        redis.scan.side_effect = [
            (1, [old_key]),  # first scan page
            (0, []),  # end of iteration
            (0, []),  # conversation scan — empty
        ]
        redis.get.return_value = old_blob
        redis.delete.return_value = 1

        with (
            patch("tasks.chat_retention.get_redis_client", return_value=redis),
            patch("tasks.chat_retention.audit_emit") as mock_emit,
        ):
            result = await _async_cleanup_expired_chats(retention_days=90)

        redis.delete.assert_called_once_with(old_key)
        assert result["deleted_sessions"] == 1
        assert result["errors"] == 0
        mock_emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_keeps_recent_session(self):
        """Sessions newer than retention_days are NOT deleted."""
        from tasks.chat_retention import _async_cleanup_expired_chats

        new_key = b"chat:session:new"
        new_blob = _session_json(days_ago=10)

        redis = MagicMock()
        redis.zremrangebyscore.return_value = 0
        redis.scan.side_effect = [
            (1, [new_key]),
            (0, []),
            (0, []),
        ]
        redis.get.return_value = new_blob

        with (
            patch("tasks.chat_retention.get_redis_client", return_value=redis),
            patch("tasks.chat_retention.audit_emit") as mock_emit,
        ):
            result = await _async_cleanup_expired_chats(retention_days=90)

        redis.delete.assert_not_called()
        assert result["deleted_sessions"] == 0
        mock_emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_keep_forever_exemption(self):
        """Sessions with keep_forever=True are skipped even if old."""
        from tasks.chat_retention import _async_cleanup_expired_chats

        key = b"chat:session:keep"
        blob = _session_json(days_ago=200, keep_forever=True)

        redis = MagicMock()
        redis.zremrangebyscore.return_value = 0
        redis.scan.side_effect = [
            (1, [key]),
            (0, []),
            (0, []),
        ]
        redis.get.return_value = blob

        with (
            patch("tasks.chat_retention.get_redis_client", return_value=redis),
            patch("tasks.chat_retention.audit_emit") as mock_emit,
        ):
            result = await _async_cleanup_expired_chats(retention_days=90)

        redis.delete.assert_not_called()
        assert result["skipped"] == 1
        mock_emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_idempotent_already_deleted(self):
        """If redis.get returns None (key already gone) → silently skip."""
        from tasks.chat_retention import _async_cleanup_expired_chats

        key = b"chat:session:gone"

        redis = MagicMock()
        redis.zremrangebyscore.return_value = 0
        redis.scan.side_effect = [
            (1, [key]),
            (0, []),
            (0, []),
        ]
        redis.get.return_value = None  # already deleted

        with (
            patch("tasks.chat_retention.get_redis_client", return_value=redis),
            patch("tasks.chat_retention.audit_emit") as mock_emit,
        ):
            result = await _async_cleanup_expired_chats(retention_days=90)

        redis.delete.assert_not_called()
        mock_emit.assert_not_called()
        assert result["errors"] == 0

    @pytest.mark.asyncio
    async def test_dry_run_does_not_delete(self):
        """dry_run=True logs intent but never calls redis.delete."""
        from tasks.chat_retention import _async_cleanup_expired_chats

        old_key = b"chat:session:old"
        old_blob = _session_json(days_ago=91)

        redis = MagicMock()
        redis.zremrangebyscore.return_value = 0
        redis.zcount.return_value = 0
        redis.scan.side_effect = [
            (1, [old_key]),
            (0, []),
            (0, []),
        ]
        redis.get.return_value = old_blob

        with (
            patch("tasks.chat_retention.get_redis_client", return_value=redis),
            patch("tasks.chat_retention.audit_emit") as mock_emit,
        ):
            result = await _async_cleanup_expired_chats(retention_days=90, dry_run=True)

        redis.delete.assert_not_called()
        mock_emit.assert_not_called()
        assert result["deleted_sessions"] == 1  # counted but not deleted

    @pytest.mark.asyncio
    async def test_audit_emit_called_per_deletion(self):
        """One audit_emit call per deleted session."""
        from tasks.chat_retention import _async_cleanup_expired_chats

        keys = [b"chat:session:a", b"chat:session:b"]
        blobs = [_session_json(days_ago=100), _session_json(days_ago=110)]

        redis = MagicMock()
        redis.zremrangebyscore.return_value = 0
        redis.scan.side_effect = [
            (1, [keys[0]]),
            (1, [keys[1]]),
            (0, []),
            (0, []),  # conversation scans
        ]
        redis.get.side_effect = blobs
        redis.delete.return_value = 1

        with (
            patch("tasks.chat_retention.get_redis_client", return_value=redis),
            patch("tasks.chat_retention.audit_emit") as mock_emit,
        ):
            result = await _async_cleanup_expired_chats(retention_days=90)

        assert mock_emit.call_count == 2
        assert result["deleted_sessions"] == 2


# ---------------------------------------------------------------------------
# file retention — _cleanup_expired_files
# ---------------------------------------------------------------------------


class TestFileRetention:
    def test_no_op_when_disabled(self, tmp_path):
        """retention_days=0 → immediate return, no files deleted."""
        from tasks.file_retention import _cleanup_expired_files

        (tmp_path / "old.txt").write_text("x")
        with patch("tasks.file_retention._STORAGE_BASE", tmp_path):
            result = _cleanup_expired_files(retention_days=0)

        assert result["deleted_files"] == 0

    def test_deletes_old_file(self, tmp_path):
        """Files older than retention_days are deleted with audit emit."""
        from tasks.file_retention import _cleanup_expired_files

        old_file = tmp_path / "old.txt"
        old_file.write_text("x")
        # backdate mtime
        import os
        import time

        old_ts = time.time() - (91 * 86400)
        os.utime(old_file, (old_ts, old_ts))

        with (
            patch("tasks.file_retention._STORAGE_BASE", tmp_path),
            patch("tasks.file_retention.audit_emit") as mock_emit,
        ):
            result = _cleanup_expired_files(retention_days=90)

        assert result["deleted_files"] == 1
        assert not old_file.exists()
        mock_emit.assert_called_once()

    def test_keeps_recent_file(self, tmp_path):
        """Files newer than retention_days are NOT deleted."""
        from tasks.file_retention import _cleanup_expired_files

        new_file = tmp_path / "new.txt"
        new_file.write_text("x")

        with (
            patch("tasks.file_retention._STORAGE_BASE", tmp_path),
            patch("tasks.file_retention.audit_emit") as mock_emit,
        ):
            result = _cleanup_expired_files(retention_days=90)

        assert result["deleted_files"] == 0
        assert new_file.exists()
        mock_emit.assert_not_called()

    def test_idempotent_already_deleted(self, tmp_path):
        """FileNotFoundError during unlink is silently ignored."""
        from tasks.file_retention import _cleanup_expired_files

        # Create a file then patch unlink to raise FileNotFoundError
        old_file = tmp_path / "gone.txt"
        old_file.write_text("x")
        import os
        import time

        old_ts = time.time() - (91 * 86400)
        os.utime(old_file, (old_ts, old_ts))

        original_unlink = old_file.__class__.unlink

        def raise_not_found(self, missing_ok=False):
            raise FileNotFoundError("already gone")

        with (
            patch("tasks.file_retention._STORAGE_BASE", tmp_path),
            patch.object(old_file.__class__, "unlink", raise_not_found),
            patch("tasks.file_retention.audit_emit") as mock_emit,
        ):
            result = _cleanup_expired_files(retention_days=90)

        assert result["errors"] == 0  # FileNotFoundError is not an error
        mock_emit.assert_not_called()

    def test_dry_run_does_not_delete(self, tmp_path):
        """dry_run=True counts but does not delete files."""
        from tasks.file_retention import _cleanup_expired_files

        old_file = tmp_path / "old.txt"
        old_file.write_text("x")
        import os
        import time

        old_ts = time.time() - (91 * 86400)
        os.utime(old_file, (old_ts, old_ts))

        with (
            patch("tasks.file_retention._STORAGE_BASE", tmp_path),
            patch("tasks.file_retention.audit_emit") as mock_emit,
        ):
            result = _cleanup_expired_files(retention_days=90, dry_run=True)

        assert result["deleted_files"] == 1
        assert old_file.exists()  # not actually deleted
        mock_emit.assert_not_called()


# ---------------------------------------------------------------------------
# audit log retention — _async_cleanup_expired_audit_logs
# ---------------------------------------------------------------------------


class TestAuditLogRetention:
    @pytest.mark.asyncio
    async def test_no_op_when_disabled(self):
        """retention_days=0 → immediate return, Redis not touched."""
        from tasks.audit_log_retention import _async_cleanup_expired_audit_logs

        with patch("tasks.audit_log_retention.get_redis_client") as mock_redis:
            result = await _async_cleanup_expired_audit_logs(retention_days=0)

        mock_redis.assert_not_called()
        assert result["deleted_logs"] == 0

    @pytest.mark.asyncio
    async def test_removes_old_entries_from_zset(self):
        """Old entries in audit: zsets are removed."""
        from tasks.audit_log_retention import _async_cleanup_expired_audit_logs

        redis = MagicMock()
        redis.scan.side_effect = [
            (1, [b"audit:unified"]),
            (0, []),
        ]
        redis.type.return_value = "zset"
        redis.zremrangebyscore.return_value = 5  # 5 entries removed

        with (
            patch("tasks.audit_log_retention.get_redis_client", return_value=redis),
            patch("tasks.audit_log_retention.audit_emit") as mock_emit,
        ):
            result = await _async_cleanup_expired_audit_logs(retention_days=90)

        assert result["deleted_logs"] == 5
        redis.zremrangebyscore.assert_called_once()
        mock_emit.assert_called_once()  # summary audit event

    @pytest.mark.asyncio
    async def test_idempotent_empty_zset(self):
        """zremrangebyscore returning 0 → no audit emit, no errors."""
        from tasks.audit_log_retention import _async_cleanup_expired_audit_logs

        redis = MagicMock()
        redis.scan.side_effect = [(1, [b"audit:unified"]), (0, [])]
        redis.type.return_value = "zset"
        redis.zremrangebyscore.return_value = 0

        with (
            patch("tasks.audit_log_retention.get_redis_client", return_value=redis),
            patch("tasks.audit_log_retention.audit_emit") as mock_emit,
        ):
            result = await _async_cleanup_expired_audit_logs(retention_days=90)

        assert result["deleted_logs"] == 0
        mock_emit.assert_not_called()  # no deletions → no event

    @pytest.mark.asyncio
    async def test_skips_non_zset_keys(self):
        """String keys under audit:* are skipped (not deleted)."""
        from tasks.audit_log_retention import _async_cleanup_expired_audit_logs

        redis = MagicMock()
        redis.scan.side_effect = [(1, [b"audit:config"]), (0, [])]
        redis.type.return_value = "string"

        with patch("tasks.audit_log_retention.get_redis_client", return_value=redis):
            result = await _async_cleanup_expired_audit_logs(retention_days=90)

        redis.zremrangebyscore.assert_not_called()
        assert result["deleted_logs"] == 0


# ---------------------------------------------------------------------------
# ssot_config defaults
# ---------------------------------------------------------------------------


class TestSsotConfigDefaults:
    def test_chat_retention_days_default_zero(self):
        """chat_retention_days defaults to 0 (disabled)."""
        from autobot_shared.ssot_config import config

        assert config.chat_retention_days == 0

    def test_file_retention_days_default_zero(self):
        """file_retention_days defaults to 0 (disabled)."""
        from autobot_shared.ssot_config import config

        assert config.file_retention_days == 0

    def test_audit_retention_days_default_zero(self):
        """audit_retention_days defaults to 0 (disabled)."""
        from autobot_shared.ssot_config import config

        assert config.audit_retention_days == 0

    def test_kb_retention_days_default_zero(self):
        """kb_retention_days defaults to 0 (disabled)."""
        from autobot_shared.ssot_config import config

        assert config.kb_retention_days == 0
