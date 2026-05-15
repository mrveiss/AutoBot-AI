# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Phase 4 observability and rollout gate tests (MVA-165, GH #7590).

Acceptance criteria pinned:
  1. Telemetry log lines emitted for chat_send and chat_response_stored
  2. Redis cardinality gauge updated after zadd to chat:recent
  3. AUTOBOT_CHAT_SSOT_STRICT=true rejects missing session_id with ValidationError
  4. AUTOBOT_CHAT_SSOT_STRICT=false (default) accepts missing session_id gracefully
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 1. Telemetry — chat_send log line
# ---------------------------------------------------------------------------


class TestChatSendTelemetry:
    """_store_and_log_user_message must emit a structured telemetry log line."""

    @pytest.mark.asyncio
    async def test_telemetry_line_emitted_on_user_message(self, caplog):
        from api.chat import _store_and_log_user_message
        from api.schemas_chat import ChatMessage

        msg = ChatMessage(content="hello", session_id="test-session-1")
        manager = MagicMock()
        manager.add_messages_batch = AsyncMock()

        with caplog.at_level(logging.INFO, logger="api.chat"):
            with patch("websocket.presence.presence_manager.broadcast_to_session", new_callable=AsyncMock):
                await _store_and_log_user_message(msg, "test-session-1", manager)

        telemetry_lines = [r.message for r in caplog.records if "event=chat_send" in r.message]
        assert len(telemetry_lines) == 1, "Must emit exactly one chat_send telemetry line"
        assert "session_id=test-session-1" in telemetry_lines[0]


# ---------------------------------------------------------------------------
# 2. Telemetry — chat_response_stored log line
# ---------------------------------------------------------------------------


class TestChatResponseStoredTelemetry:
    """_store_and_log_ai_response must emit a structured telemetry log line."""

    @pytest.mark.asyncio
    async def test_telemetry_line_emitted_on_ai_response(self, caplog):
        from api.chat import _store_and_log_ai_response

        manager = MagicMock()
        manager.add_messages_batch = AsyncMock()
        ai_response = {"content": "Hi there", "metadata": {}}

        with caplog.at_level(logging.INFO, logger="api.chat"):
            await _store_and_log_ai_response(ai_response, "test-session-2", "req-abc", manager)

        telemetry_lines = [r.message for r in caplog.records if "event=chat_response_stored" in r.message]
        assert len(telemetry_lines) == 1, "Must emit exactly one chat_response_stored telemetry line"
        assert "session_id=test-session-2" in telemetry_lines[0]


# ---------------------------------------------------------------------------
# 3. Redis cardinality gauge
# ---------------------------------------------------------------------------


class TestChatRecentCardinalityGauge:
    """After zadd, _update_redis_cache_on_save must log cardinality and update gauge."""

    @pytest.mark.asyncio
    async def test_cardinality_logged_after_zadd(self, caplog):
        from chat_history.session import SessionMixin
        from constants.redis_constants import REDIS_KEY

        class _StubManager(SessionMixin):
            def __init__(self):
                self.redis_client = MagicMock()
                self._async_cache_session = AsyncMock()
                self.max_session_files = 50

        mgr = _StubManager()
        call_log: list = []

        zadd_fn = mgr.redis_client.zadd
        zremrangebyrank_fn = mgr.redis_client.zremrangebyrank
        zcard_fn = mgr.redis_client.zcard

        async def _fake_executor(fn, *args):
            if fn is zadd_fn:
                call_log.append(("zadd", args))
            elif fn is zremrangebyrank_fn:
                call_log.append(("zremrangebyrank", args))
            elif fn is zcard_fn:
                call_log.append(("zcard", args))
                return 42  # simulated cardinality

        with patch("chat_history.session.run_in_chat_io_executor", side_effect=_fake_executor):
            with patch("monitoring.prometheus_metrics.get_metrics_manager") as mock_metrics:
                mock_metrics.return_value.set_chat_recent_cardinality = MagicMock()
                with caplog.at_level(logging.INFO, logger="chat_history.session"):
                    await mgr._update_redis_cache_on_save("sess-xyz", {"session_id": "sess-xyz"})

        assert ("zcard", (REDIS_KEY.CHAT_RECENT,)) in call_log, "zcard must be called for cardinality"
        cardinality_lines = [
            r.message for r in caplog.records if "event=chat_recent_cardinality" in r.message
        ]
        assert len(cardinality_lines) == 1
        assert "value=42" in cardinality_lines[0]


# ---------------------------------------------------------------------------
# 4. Feature flag: SSOT strict mode
# ---------------------------------------------------------------------------


class TestSSOTStrictMode:
    """AUTOBOT_CHAT_SSOT_STRICT=true must reject missing session_id."""

    def test_strict_mode_rejects_missing_session_id(self):
        import importlib

        with patch.dict("os.environ", {"AUTOBOT_CHAT_SSOT_STRICT": "true"}):
            import api.chat as chat_module

            importlib.reload(chat_module)
            # Reload to pick up env var at module level
            assert chat_module._CHAT_SSOT_STRICT is True, "Flag must be set in strict mode"

    def test_default_mode_is_lenient(self):
        import importlib

        with patch.dict("os.environ", {"AUTOBOT_CHAT_SSOT_STRICT": "false"}):
            import api.chat as chat_module

            importlib.reload(chat_module)
            assert chat_module._CHAT_SSOT_STRICT is False, "Default must be lenient (false)"

    def test_strict_validate_session_id_raises_on_none(self):
        """In strict mode _validate_session_id must raise on None session_id."""
        with patch("api.chat._CHAT_SSOT_STRICT", True):
            from api.chat import _validate_session_id

            with pytest.raises(Exception, match="session_id is required"):
                _validate_session_id(None)

    def test_lenient_validate_session_id_passes_on_none(self):
        """In lenient mode _validate_session_id must not raise on None."""
        with patch("api.chat._CHAT_SSOT_STRICT", False):
            from api.chat import _validate_session_id

            _validate_session_id(None)  # must not raise
