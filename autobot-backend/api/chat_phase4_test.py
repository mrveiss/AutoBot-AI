# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Phase 4 observability and rollout gate tests (MVA-165, GH #7590).

Acceptance criteria pinned:
  1. Telemetry log lines are valid JSON with required keys
  2. chat_send emits JSON {"event": "chat_send", "session_id": ..., "message_id": ...}
  3. chat_response_stored emits JSON {"event": "chat_response_stored", ...}
  4. Prometheus counter incremented for each event type
  5. Redis cardinality gauge updated after zadd to chat:recent
  6. cardinality log line is valid JSON with event + value keys
  7. AUTOBOT_CHAT_SSOT_STRICT=true rejects missing session_id with ValidationError
  8. AUTOBOT_CHAT_SSOT_STRICT=false (default) accepts missing session_id gracefully
"""

from __future__ import annotations

import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _find_telemetry(records: list, event_name: str) -> list[dict]:
    """Extract and parse JSON telemetry lines matching `event` == event_name."""
    result = []
    for r in records:
        try:
            data = json.loads(r.message)
            if data.get("event") == event_name:
                result.append(data)
        except (json.JSONDecodeError, ValueError):
            pass
    return result


# ---------------------------------------------------------------------------
# 1+2. chat_send telemetry — JSON format
# ---------------------------------------------------------------------------


class TestChatSendTelemetry:
    """_store_and_log_user_message must emit valid JSON telemetry."""

    @pytest.mark.asyncio
    async def test_json_telemetry_emitted_on_user_message(self, caplog):
        from api.chat import _store_and_log_user_message
        from api.schemas_chat import ChatMessage

        msg = ChatMessage(content="hello", session_id="test-session-1")
        manager = MagicMock()
        manager.add_messages_batch = AsyncMock()

        with caplog.at_level(logging.INFO, logger="api.chat"):
            with patch("websocket.presence.presence_manager.broadcast_to_session", new_callable=AsyncMock):
                with patch("monitoring.prometheus_metrics.get_metrics_manager") as mock_metrics:
                    mock_metrics.return_value.record_chat_message_sent = MagicMock()
                    await _store_and_log_user_message(msg, "test-session-1", manager)

        matches = _find_telemetry(caplog.records, "chat_send")
        assert len(matches) == 1, "Must emit exactly one chat_send JSON telemetry line"
        ev = matches[0]
        assert ev["session_id"] == "test-session-1", "session_id must match"
        assert "message_id" in ev, "message_id must be present"

    @pytest.mark.asyncio
    async def test_prometheus_counter_incremented_on_chat_send(self, caplog):
        from api.chat import _store_and_log_user_message
        from api.schemas_chat import ChatMessage

        msg = ChatMessage(content="hello", session_id="test-session-counter")
        manager = MagicMock()
        manager.add_messages_batch = AsyncMock()

        with patch("websocket.presence.presence_manager.broadcast_to_session", new_callable=AsyncMock):
            with patch("monitoring.prometheus_metrics.get_metrics_manager") as mock_metrics:
                record_fn = MagicMock()
                mock_metrics.return_value.record_chat_message_sent = record_fn
                await _store_and_log_user_message(msg, "test-session-counter", manager)

        record_fn.assert_called_once_with("chat_send")


# ---------------------------------------------------------------------------
# 3+4. chat_response_stored telemetry — JSON format
# ---------------------------------------------------------------------------


class TestChatResponseStoredTelemetry:
    """_store_and_log_ai_response must emit valid JSON telemetry."""

    @pytest.mark.asyncio
    async def test_json_telemetry_emitted_on_ai_response(self, caplog):
        from api.chat import _store_and_log_ai_response

        manager = MagicMock()
        manager.add_messages_batch = AsyncMock()
        ai_response = {"content": "Hi there", "metadata": {}}

        with caplog.at_level(logging.INFO, logger="api.chat"):
            with patch("monitoring.prometheus_metrics.get_metrics_manager") as mock_metrics:
                mock_metrics.return_value.record_chat_message_sent = MagicMock()
                await _store_and_log_ai_response(ai_response, "test-session-2", "req-abc", manager)

        matches = _find_telemetry(caplog.records, "chat_response_stored")
        assert len(matches) == 1, "Must emit exactly one chat_response_stored telemetry line"
        ev = matches[0]
        assert ev["session_id"] == "test-session-2"
        assert "message_id" in ev

    @pytest.mark.asyncio
    async def test_prometheus_counter_incremented_on_response_stored(self):
        from api.chat import _store_and_log_ai_response

        manager = MagicMock()
        manager.add_messages_batch = AsyncMock()
        ai_response = {"content": "reply", "metadata": {}}

        with patch("monitoring.prometheus_metrics.get_metrics_manager") as mock_metrics:
            record_fn = MagicMock()
            mock_metrics.return_value.record_chat_message_sent = record_fn
            await _store_and_log_ai_response(ai_response, "sess-x", "req-x", manager)

        record_fn.assert_called_once_with("chat_response_stored")


# ---------------------------------------------------------------------------
# 5+6. Redis cardinality gauge
# ---------------------------------------------------------------------------


class TestChatRecentCardinalityGauge:
    """After zadd, _update_redis_cache_on_save must log JSON cardinality and update gauge."""

    @pytest.mark.asyncio
    async def test_cardinality_json_logged_and_gauge_updated(self, caplog):
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
                return 42

        cardinality_set: list[int] = []

        with patch("chat_history.session.run_in_chat_io_executor", side_effect=_fake_executor):
            with patch("monitoring.prometheus_metrics.get_metrics_manager") as mock_mgr:
                mock_mgr.return_value.set_chat_recent_cardinality = lambda v: cardinality_set.append(v)
                with caplog.at_level(logging.INFO, logger="chat_history.session"):
                    await mgr._update_redis_cache_on_save("sess-xyz", {"session_id": "sess-xyz"})

        # zcard must be called
        assert ("zcard", (REDIS_KEY.CHAT_RECENT,)) in call_log

        # Log line must be valid JSON with expected keys
        cardinality_lines = _find_telemetry(caplog.records, "chat_recent_cardinality")
        assert len(cardinality_lines) == 1
        assert cardinality_lines[0]["value"] == 42

        # Prometheus gauge must be updated with the cardinality value
        assert 42 in cardinality_set, "Prometheus gauge must receive the zcard value"


# ---------------------------------------------------------------------------
# 7. Prometheus counter and gauge via ChatMetricsRecorder
# ---------------------------------------------------------------------------


class TestChatMetricsRecorder:
    """ChatMetricsRecorder must correctly update metrics."""

    def test_record_message_sent_increments_counter(self):
        from prometheus_client import CollectorRegistry

        from autobot_shared.monitoring.metrics.chat import ChatMetricsRecorder

        registry = CollectorRegistry()
        recorder = ChatMetricsRecorder(registry)
        recorder.record_message_sent("chat_send")
        recorder.record_message_sent("chat_send")
        recorder.record_message_sent("chat_response_stored")

        # Read back counter values
        send_val = recorder.messages_sent_total.labels(event_type="chat_send")._value.get()
        resp_val = recorder.messages_sent_total.labels(event_type="chat_response_stored")._value.get()
        assert send_val == 2.0
        assert resp_val == 1.0

    def test_set_recent_cardinality_updates_gauge(self):
        from prometheus_client import CollectorRegistry

        from autobot_shared.monitoring.metrics.chat import ChatMetricsRecorder

        registry = CollectorRegistry()
        recorder = ChatMetricsRecorder(registry)
        recorder.set_recent_cardinality(57)

        assert recorder.recent_cardinality._value.get() == 57.0


# ---------------------------------------------------------------------------
# 8+9. Feature flag: SSOT strict mode
# ---------------------------------------------------------------------------


class TestSSOTStrictMode:
    """AUTOBOT_CHAT_SSOT_STRICT=true must reject missing session_id."""

    def test_strict_mode_flag_reads_env(self):
        import importlib

        with patch.dict("os.environ", {"AUTOBOT_CHAT_SSOT_STRICT": "true"}):
            import api.chat as chat_module

            importlib.reload(chat_module)
            assert chat_module._CHAT_SSOT_STRICT is True

    def test_default_mode_is_lenient(self):
        import importlib

        with patch.dict("os.environ", {"AUTOBOT_CHAT_SSOT_STRICT": "false"}):
            import api.chat as chat_module

            importlib.reload(chat_module)
            assert chat_module._CHAT_SSOT_STRICT is False

    def test_strict_validate_session_id_raises_on_none(self):
        with patch("api.chat._CHAT_SSOT_STRICT", True):
            from api.chat import _validate_session_id

            with pytest.raises(Exception, match="session_id is required"):
                _validate_session_id(None)

    def test_lenient_validate_session_id_passes_on_none(self):
        with patch("api.chat._CHAT_SSOT_STRICT", False):
            from api.chat import _validate_session_id

            _validate_session_id(None)  # must not raise
