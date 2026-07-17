# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for HealthCollector state-change pub/sub logic (#3404)."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from slm.agent.health_collector import _STATE_CHANGE_CHANNEL_TEMPLATE, HealthCollector

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_collector() -> HealthCollector:
    """Return a HealthCollector with service discovery disabled."""
    return HealthCollector(discover_services=False)


def _svc(name: str, status: str, error_message: str = "") -> dict:
    base = {"name": name, "status": status}
    if error_message:
        base["error_message"] = error_message
    return base


# ---------------------------------------------------------------------------
# _detect_and_publish_state_changes
# ---------------------------------------------------------------------------


class TestDetectAndPublishStateChanges:
    def test_first_observation_does_not_publish(self):
        collector = _make_collector()
        with patch.object(collector, "_publish_state_change") as mock_pub:
            collector._detect_and_publish_state_changes([_svc("nginx", "running")])
        mock_pub.assert_not_called()

    def test_first_observation_stores_state(self):
        collector = _make_collector()
        collector._detect_and_publish_state_changes([_svc("nginx", "running")])
        assert collector._last_known_status["nginx"] == "running"

    def test_same_state_does_not_publish(self):
        collector = _make_collector()
        collector._last_known_status["nginx"] = "running"
        with patch.object(collector, "_publish_state_change") as mock_pub:
            collector._detect_and_publish_state_changes([_svc("nginx", "running")])
        mock_pub.assert_not_called()

    def test_state_change_publishes_event(self):
        collector = _make_collector()
        collector._last_known_status["nginx"] = "running"
        with patch.object(collector, "_publish_state_change") as mock_pub:
            collector._detect_and_publish_state_changes([_svc("nginx", "failed")])
        mock_pub.assert_called_once_with(
            service_name="nginx",
            prev_state="running",
            new_state="failed",
            error_context="",
        )

    def test_error_context_forwarded_on_failure(self):
        collector = _make_collector()
        collector._last_known_status["redis"] = "running"
        with patch.object(collector, "_publish_state_change") as mock_pub:
            collector._detect_and_publish_state_changes([_svc("redis", "failed", error_message="OOM killed")])
        _, kwargs = mock_pub.call_args
        assert kwargs["error_context"] == "OOM killed"

    def test_updates_last_known_status_on_change(self):
        collector = _make_collector()
        collector._last_known_status["nginx"] = "running"
        collector._detect_and_publish_state_changes([_svc("nginx", "failed")])
        assert collector._last_known_status["nginx"] == "failed"

    def test_service_without_name_is_skipped(self):
        collector = _make_collector()
        with patch.object(collector, "_publish_state_change") as mock_pub:
            collector._detect_and_publish_state_changes([{"status": "failed"}])
        mock_pub.assert_not_called()

    def test_multiple_services_each_evaluated_independently(self):
        collector = _make_collector()
        collector._last_known_status["nginx"] = "running"
        collector._last_known_status["sshd"] = "running"
        with patch.object(collector, "_publish_state_change") as mock_pub:
            collector._detect_and_publish_state_changes([_svc("nginx", "failed"), _svc("sshd", "running")])
        assert mock_pub.call_count == 1
        args = mock_pub.call_args
        assert args.kwargs["service_name"] == "nginx"


# ---------------------------------------------------------------------------
# _publish_state_change
# ---------------------------------------------------------------------------


class TestPublishStateChange:
    def _mock_redis(self):
        mock = MagicMock()
        mock.publish = MagicMock(return_value=1)
        return mock

    def test_publishes_to_correct_channel(self):
        collector = _make_collector()
        mock_redis = self._mock_redis()
        with patch("slm.agent.health_collector.get_redis_client", return_value=mock_redis):
            collector._publish_state_change("nginx", "running", "failed", "")
        expected_channel = _STATE_CHANGE_CHANNEL_TEMPLATE.format(service="nginx")
        call_args = mock_redis.publish.call_args[0]
        assert call_args[0] == expected_channel

    def test_payload_contains_required_fields(self):
        collector = _make_collector()
        collector.hostname = "test-host"
        mock_redis = self._mock_redis()
        captured = {}

        def _capture_publish(channel, payload):
            captured["payload"] = json.loads(payload)

        mock_redis.publish.side_effect = _capture_publish
        with patch("slm.agent.health_collector.get_redis_client", return_value=mock_redis):
            collector._publish_state_change("nginx", "running", "failed", "segfault")

        p = captured["payload"]
        assert p["service"] == "nginx"
        assert p["hostname"] == "test-host"
        assert p["prev_state"] == "running"
        assert p["new_state"] == "failed"
        assert p["error_context"] == "segfault"

    def test_redis_unavailable_does_not_raise(self):
        collector = _make_collector()
        with patch("slm.agent.health_collector.get_redis_client", return_value=None):
            # Must not propagate any exception.
            collector._publish_state_change("nginx", "running", "failed", "")

    def test_redis_exception_does_not_raise(self):
        collector = _make_collector()
        mock_redis = self._mock_redis()
        mock_redis.publish.side_effect = ConnectionError("redis gone")
        with patch("slm.agent.health_collector.get_redis_client", return_value=mock_redis):
            collector._publish_state_change("nginx", "running", "failed", "")


# ---------------------------------------------------------------------------
# NotificationEvent.SERVICE_FAILED round-trip (import smoke test)
# ---------------------------------------------------------------------------

# The consumer of the published event is autobot-backend's NotificationService
# (the OTHER backend) — "services.notification_service" does not exist in the
# slm-backend tree, so the bare import could never resolve here (#11798).
# Spec-load the real module from the repo checkout under a private name, with
# its environment-bound deps stubbed (ssot_config reads /etc/autobot).  Skip
# when the sibling checkout is not present (deployment layouts).  Resolved by
# upward search so the slm/agent and ansible copies (drift-checked identical)
# both find the repo root from their different depths.


def _find_backend_notif_path():
    for _parent in Path(__file__).resolve().parents:
        _cand = _parent / "autobot-backend" / "services" / "notification_service.py"
        if _cand.exists():
            return _cand
    return None


_BACKEND_NOTIF_PATH = _find_backend_notif_path()


def _load_backend_notification_service():
    import importlib.util

    stubs = {
        "constants": MagicMock(),
        "constants.ttl_constants": MagicMock(TTL_7_DAYS=7 * 24 * 3600),
        "autobot_shared.ssot_config": MagicMock(config=MagicMock()),
        "autobot_shared.redis_client": MagicMock(),
        "autobot_shared.logging_manager": MagicMock(get_logger=MagicMock(return_value=MagicMock())),
    }
    with patch.dict(sys.modules, stubs):
        spec = importlib.util.spec_from_file_location("_backend_notification_service", _BACKEND_NOTIF_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod


class TestServiceFailedEvent:
    @pytest.mark.skipif(_BACKEND_NOTIF_PATH is None, reason="autobot-backend checkout not present (env-bound)")
    def test_service_failed_enum_value(self):
        mod = _load_backend_notification_service()

        assert mod.NotificationEvent.SERVICE_FAILED.value == "service_failed"

    @pytest.mark.skipif(_BACKEND_NOTIF_PATH is None, reason="autobot-backend checkout not present (env-bound)")
    def test_service_failed_template_renders(self):
        mod = _load_backend_notification_service()

        svc = mod.NotificationService()
        result = svc.render_template(
            mod.NotificationEvent.SERVICE_FAILED.value,
            {
                "service": "nginx",
                "hostname": "node-01",
                "prev_state": "running",
                "new_state": "failed",
                "error_context": "OOM killed",
            },
        )
        assert "nginx" in result
        assert "node-01" in result
        assert "running" in result
        assert "failed" in result
