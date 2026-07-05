# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for /api/rum/event schema and log write path (#10938).

Validates:
- RumEvent pydantic model accepts the exact shape the frontend sends
- log_rum_event handler writes a log line when rum_config["enabled"] is True
- rum_config["enabled"] defaults to True
- handler short-circuits cleanly when disabled (no exception)
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from api.schemas_analytics import RumEvent

# ---------------------------------------------------------------------------
# RumEvent schema validation
# ---------------------------------------------------------------------------


class TestRumEventSchema:
    """RumEvent must accept the exact payload the frontend sends."""

    _BASE = {
        "type": "javascript_error",
        "timestamp": "2026-07-05T12:00:00.000Z",
        "sessionId": "rum_deadbeef_1234567890",
        "url": "http://localhost:5173/dashboard",
        "userAgent": "Mozilla/5.0 (Test)",
        "data": {
            "message": "Cannot read properties of undefined",
            "filename": "http://localhost:5173/assets/index.js",
            "lineno": 42,
            "colno": 7,
            "stack": "TypeError: Cannot read...",
        },
    }

    def test_full_payload_validates(self):
        event = RumEvent(**self._BASE)
        assert event.type == "javascript_error"
        assert event.sessionId == "rum_deadbeef_1234567890"
        assert event.data["message"] == "Cannot read properties of undefined"

    def test_data_defaults_to_empty_dict(self):
        payload = {k: v for k, v in self._BASE.items() if k != "data"}
        event = RumEvent(**payload)
        assert event.data == {}

    def test_component_error_payload(self):
        payload = {**self._BASE, "type": "component_error", "data": {"message": "Vue error", "component": "ChatView"}}
        event = RumEvent(**payload)
        assert event.type == "component_error"
        assert event.data["component"] == "ChatView"

    def test_promise_rejection_payload(self):
        payload = {**self._BASE, "type": "unhandled_promise_rejection", "data": {"reason": "Network error"}}
        event = RumEvent(**payload)
        assert event.data["reason"] == "Network error"

    def test_missing_required_field_raises(self):
        payload = {k: v for k, v in self._BASE.items() if k != "sessionId"}
        with pytest.raises(ValidationError):
            RumEvent(**payload)

    def test_missing_url_raises(self):
        payload = {k: v for k, v in self._BASE.items() if k != "url"}
        with pytest.raises(ValidationError):
            RumEvent(**payload)


# ---------------------------------------------------------------------------
# rum_config["enabled"] default
# ---------------------------------------------------------------------------


class TestRumConfigDefault:
    def test_enabled_defaults_to_true(self):
        from api.rum import rum_config

        assert rum_config["enabled"] is True, (
            "rum_config['enabled'] must default to True so events are logged on startup; "
            "was False, causing rum.log to be empty since Jun 18."
        )


# ---------------------------------------------------------------------------
# log_rum_event handler writes to the RUM logger
# ---------------------------------------------------------------------------


class TestLogRumEventHandler:
    """Verify the handler logs when enabled and is silent when disabled."""

    _VALID_EVENT = RumEvent(
        type="javascript_error",
        timestamp="2026-07-05T12:00:00.000Z",
        sessionId="rum_test_session",
        url="http://localhost:5173/",
        userAgent="pytest/test",
        data={"message": "test error", "filename": "test.js", "lineno": 1},
    )

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_handler_logs_when_enabled(self):
        """Handler must log the event at some level when rum_config['enabled'] is True.

        javascript_error is not in _ERROR_EVENT_TYPES (which only has "error" and
        "promise_rejection") so _log_rum_event_by_type falls through to info-level.
        We assert that at least one logging call was made and that the session ID
        and error message appear in it.
        """
        import api.rum as rum_module

        original_enabled = rum_module.rum_config["enabled"]
        logged_calls: list = []

        def capture_any(msg, *args, **kwargs):
            logged_calls.append(msg)

        try:
            rum_module.rum_config["enabled"] = True
            mock_logger = MagicMock()
            # Capture both .info and .error calls
            mock_logger.info.side_effect = capture_any
            mock_logger.error.side_effect = capture_any
            rum_module.rum_logger = mock_logger

            result = self._run(rum_module.log_rum_event(self._VALID_EVENT))

            assert result["status"] == "success", f"Expected success, got: {result}"
            assert len(logged_calls) == 1, f"Expected exactly 1 log call, got {len(logged_calls)}: {logged_calls}"
            assert "SESSION=rum_test_session" in logged_calls[0]
            assert "test error" in logged_calls[0]
        finally:
            rum_module.rum_config["enabled"] = original_enabled
            rum_module.rum_logger = rum_module.setup_rum_logger()

    def test_handler_returns_disabled_when_config_disabled(self):
        import api.rum as rum_module

        original_enabled = rum_module.rum_config["enabled"]
        try:
            rum_module.rum_config["enabled"] = False
            mock_logger = MagicMock()

            with patch.object(rum_module, "rum_logger", mock_logger):
                result = self._run(rum_module.log_rum_event(self._VALID_EVENT))

            assert result["status"] == "disabled"
            mock_logger.error.assert_not_called()
        finally:
            rum_module.rum_config["enabled"] = original_enabled
