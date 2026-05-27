# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Phase 2 backend persistence consolidation tests (Issue #7572).

Pins four acceptance criteria from the SSOT design:
  1. ChatMessage / EnhancedChatMessage require session_id (→ 422 when absent)
  2. process_enhanced_chat_message returns HTTP 422 for invalid session_id format
  3. chat:recent sorted-set has TTL applied after every zadd
  4. save_session writes disk before updating Redis cache
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# 1. Schema-level enforcement: session_id is required (no fallback generation)
# ---------------------------------------------------------------------------


class TestSessionIdRequired:
    """ChatMessage and EnhancedChatMessage must reject requests missing session_id."""

    def test_chat_message_without_session_id_raises_422_schema_error(self):
        from api.schemas_chat import ChatMessage

        with pytest.raises(ValidationError) as exc_info:
            ChatMessage(content="hello")

        errors = exc_info.value.errors()
        assert any(
            e["loc"] == ("session_id",) for e in errors
        ), "Pydantic must flag session_id as missing — FastAPI surfaces this as HTTP 422"

    def test_enhanced_chat_message_without_session_id_raises_422_schema_error(self):
        from api.schemas_chat import EnhancedChatMessage

        with pytest.raises(ValidationError) as exc_info:
            EnhancedChatMessage(content="hello")

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("session_id",) for e in errors)

    def test_chat_message_with_session_id_is_accepted(self):
        from api.schemas_chat import ChatMessage

        msg = ChatMessage(content="hello", session_id="abc-123")
        assert msg.session_id == "abc-123"

    def test_enhanced_chat_message_with_session_id_is_accepted(self):
        from api.schemas_chat import EnhancedChatMessage

        msg = EnhancedChatMessage(content="hello", session_id="abc-123")
        assert msg.session_id == "abc-123"


# ---------------------------------------------------------------------------
# 2. process_enhanced_chat_message returns HTTP 422 for invalid session_id
# ---------------------------------------------------------------------------


class TestEnhancedChatMessage422:
    """process_enhanced_chat_message raises HTTPException(422) for bad format."""

    @pytest.mark.asyncio
    async def test_invalid_session_id_format_raises_422(self):
        from fastapi import HTTPException

        from api.chat import process_enhanced_chat_message
        from api.schemas_chat import EnhancedChatMessage

        with patch("api.chat.validate_chat_session_id", return_value=False):
            msg = EnhancedChatMessage(content="hello", session_id="BAD_FORMAT")
            with pytest.raises(HTTPException) as exc_info:
                await process_enhanced_chat_message(
                    message=msg,
                    chat_history_manager=MagicMock(),
                    knowledge_base=None,
                    config={},
                    request_id="r-test",
                )

        assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# 3. chat:recent is capped via ZREMRANGEBYRANK (not sliding-window EXPIRE)
# ---------------------------------------------------------------------------


class TestChatRecentZremrangebyrank:
    """_update_redis_cache_on_save must cap chat:recent with ZREMRANGEBYRANK, not EXPIRE."""

    @pytest.mark.asyncio
    async def test_zremrangebyrank_called_after_zadd_on_chat_recent(self):
        from chat_history.session import SessionMixin
        from constants.redis_constants import REDIS_KEY

        class _StubManager(SessionMixin):
            def __init__(self):
                self.redis_client = MagicMock()
                self._async_cache_session = AsyncMock()
                self.max_session_files = 50

        mgr = _StubManager()

        call_log: list[tuple] = []

        zadd_fn = mgr.redis_client.zadd
        zremrangebyrank_fn = mgr.redis_client.zremrangebyrank

        async def _fake_executor(fn, *args):
            if fn is zadd_fn:
                call_log.append(("zadd", args))
            elif fn is zremrangebyrank_fn:
                call_log.append(("zremrangebyrank", args))
            elif fn is mgr.redis_client.expire:
                call_log.append(("expire", args))

        with patch("chat_history.session.run_in_chat_io_executor", side_effect=_fake_executor):
            await mgr._update_redis_cache_on_save("sess-abc", {"session_id": "sess-abc"})

        names = [e[0] for e in call_log]
        assert "zadd" in names, "zadd must be called"
        assert "zremrangebyrank" in names, "zremrangebyrank must be called to cap set size"
        assert "expire" not in names, "expire must NOT be called (sliding-window anti-pattern)"
        assert names.index("zadd") < names.index("zremrangebyrank"), "zadd must precede zremrangebyrank"

        zrem_args = next(e[1] for e in call_log if e[0] == "zremrangebyrank")
        assert zrem_args[0] == REDIS_KEY.CHAT_RECENT, "must use REDIS_KEY.CHAT_RECENT constant"
        assert zrem_args[1] == 0, "must remove from rank 0"
        assert zrem_args[2] == -(mgr.max_session_files + 1), "must keep max_session_files most recent entries"


# ---------------------------------------------------------------------------
# 4. Disk write precedes Redis update in save_session
# ---------------------------------------------------------------------------


class TestDiskWriteBeforeRedis:
    """save_session must write disk before updating Redis cache."""

    @pytest.mark.asyncio
    async def test_disk_written_before_redis_update(self):
        from chat_history.session import SessionMixin

        class _StubManager(SessionMixin):
            def __init__(self):
                self.redis_client = None
                self.max_messages = 100
                self.max_session_files = 500
                self._counter_lock = MagicMock()
                self._session_save_counter = 0
                self.memory_graph = None
                self.memory_graph_enabled = False

            def _sanitize_session_id(self, _):
                pass

            def _get_chats_directory(self):
                return "/tmp/chat_test"  # nosec B108 - test/controlled code uses tmpdir intentionally

            async def _ensure_chats_directory_exists(self, _):
                pass

            async def _load_existing_chat_data(self, *_):
                return {}

            def _build_session_chat_data(self, *args):
                return {"session_id": args[1]}

            async def _handle_periodic_cleanup(self):
                pass

        mgr = _StubManager()
        call_order: list[str] = []

        async def _fake_write(chat_file, chat_data):
            call_order.append("disk")

        async def _fake_cache(session_id, chat_data):
            call_order.append("redis")

        mgr._write_session_to_storage = _fake_write
        mgr._update_redis_cache_on_save = _fake_cache

        with patch(
            "autobot_shared.security.path_validator.validate_relative_path", return_value="/tmp/s.json"  # nosec B108 - test/controlled code uses tmpdir intentionally
        ):
            await mgr.save_session("sess-xyz")

        assert call_order == ["disk", "redis"], f"Expected disk before redis, got {call_order}"
