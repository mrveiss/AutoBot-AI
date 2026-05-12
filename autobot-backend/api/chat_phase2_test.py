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

from unittest.mock import AsyncMock, MagicMock, call, patch

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
        assert any(e["loc"] == ("session_id",) for e in errors), (
            "Pydantic must flag session_id as missing — FastAPI surfaces this as HTTP 422"
        )

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
# 3. chat:recent TTL is set after each zadd
# ---------------------------------------------------------------------------


class TestChatRecentTTL:
    """_update_redis_cache_on_save must call expire on chat:recent after zadd."""

    @pytest.mark.asyncio
    async def test_expire_called_after_zadd_on_chat_recent(self):
        from chat_history.cache import _CHAT_SESSION_CACHE_TTL
        from chat_history.session import SessionMixin

        # Minimal concrete class that satisfies SessionMixin's redis dependency.
        class _StubManager(SessionMixin):
            def __init__(self):
                self.redis_client = MagicMock()
                self._async_cache_session = AsyncMock()

        mgr = _StubManager()

        # Use list of (name, args) tuples to record executor calls in order.
        call_log: list[tuple] = []

        # zadd_fn and expire_fn captured after mgr is constructed so identity checks work.
        zadd_fn = mgr.redis_client.zadd
        expire_fn = mgr.redis_client.expire

        async def _fake_executor(fn, *args):
            if fn is zadd_fn:
                call_log.append(("zadd", args))
            elif fn is expire_fn:
                call_log.append(("expire", args))

        with patch("chat_history.session.run_in_chat_io_executor", side_effect=_fake_executor):
            await mgr._update_redis_cache_on_save("sess-abc", {"session_id": "sess-abc"})

        names = [e[0] for e in call_log]
        assert "zadd" in names, "zadd must be called"
        assert "expire" in names, "expire must be called after zadd"
        assert names.index("zadd") < names.index("expire"), "zadd must precede expire"

        expire_args = next(e[1] for e in call_log if e[0] == "expire")
        assert expire_args[0] == "chat:recent"
        assert expire_args[1] == _CHAT_SESSION_CACHE_TTL


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
                return "/tmp/chat_test"

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

        with patch("autobot_shared.security.path_validator.validate_relative_path", return_value="/tmp/s.json"):
            await mgr.save_session("sess-xyz")

        assert call_order == ["disk", "redis"], (
            f"Expected disk before redis, got {call_order}"
        )
