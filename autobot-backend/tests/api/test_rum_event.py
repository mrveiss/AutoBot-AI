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
        # #13113: asyncio.run() — pytest-asyncio owns the loop lifecycle, so a sync test
        # running before any async test on its worker had no current loop for get_event_loop().
        return asyncio.run(coro)

    def test_handler_logs_frontend_error_at_error_level(self):
        """#10938: a frontend `javascript_error` must be logged at ERROR level.

        Previously `_ERROR_EVENT_TYPES` only held {"error","promise_rejection"},
        which matched none of the type strings the frontend actually sends, so
        every client error fell through to INFO and was indistinguishable from
        perf/interaction events.
        """
        import api.rum as rum_module

        original_enabled = rum_module.rum_config["enabled"]
        try:
            rum_module.rum_config["enabled"] = True
            mock_logger = MagicMock()
            rum_module.rum_logger = mock_logger

            result = self._run(rum_module.log_rum_event(self._VALID_EVENT))

            assert result["status"] == "success", f"Expected success, got: {result}"
            # Routed to ERROR, not INFO.
            mock_logger.error.assert_called_once()
            mock_logger.info.assert_not_called()
            msg = mock_logger.error.call_args.args[0]
            assert "SESSION=rum_test_session" in msg
            assert "test error" in msg
        finally:
            rum_module.rum_config["enabled"] = original_enabled
            rum_module.rum_logger = rum_module.setup_rum_logger()

    def test_all_frontend_error_types_route_to_error_level(self):
        """#10938: every genuine frontend error type maps to ERROR level."""
        import api.rum as rum_module

        original_enabled = rum_module.rum_config["enabled"]
        try:
            rum_module.rum_config["enabled"] = True
            for etype in ("javascript_error", "unhandled_promise_rejection", "component_error"):
                mock_logger = MagicMock()
                rum_module.rum_logger = mock_logger
                event = RumEvent(
                    type=etype,
                    timestamp="2026-07-05T12:00:00.000Z",
                    sessionId="s",
                    url="http://localhost/",
                    userAgent="pytest",
                    data={"message": "boom"},
                )
                self._run(rum_module.log_rum_event(event))
                mock_logger.error.assert_called_once()
                mock_logger.info.assert_not_called()
        finally:
            rum_module.rum_config["enabled"] = original_enabled
            rum_module.rum_logger = rum_module.setup_rum_logger()

    def test_performance_event_routes_to_info_level(self):
        """A non-error type (performance) must stay at INFO, not ERROR."""
        import api.rum as rum_module

        original_enabled = rum_module.rum_config["enabled"]
        try:
            rum_module.rum_config["enabled"] = True
            mock_logger = MagicMock()
            rum_module.rum_logger = mock_logger
            event = RumEvent(
                type="performance",
                timestamp="2026-07-05T12:00:00.000Z",
                sessionId="s",
                url="http://localhost/",
                userAgent="pytest",
                data={"metric": "lcp", "value": 1200},
            )
            self._run(rum_module.log_rum_event(event))
            mock_logger.info.assert_called_once()
            mock_logger.error.assert_not_called()
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
