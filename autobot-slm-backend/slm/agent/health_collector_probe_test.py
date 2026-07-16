# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the app-level /health probe in HealthCollector (#11723/#11777).

The probe feeds engine_degraded/degraded_reason from a service's own
/health endpoint into the heartbeat service dict, which the SLM backend
merges into Service.extra_data (services/service_extra_data.py, #11718).

This is the CANONICAL tree (autobot-slm-backend/slm/agent/) — the one the
Ansible slm_agent role actually deploys. #11723's original probe landed in
the non-deployed autobot-slm-agent/ tree, leaving it inert in prod (#11777).
"""

import json
from unittest.mock import MagicMock, patch

from slm.agent.health_collector import HealthCollector


def _collector() -> HealthCollector:
    return HealthCollector(discover_services=False)


def _fake_response(body: bytes):
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda self: self
    resp.__exit__ = lambda self, *a: False
    return resp


def test_unmapped_service_not_probed():
    with patch("slm.agent.health_collector.urllib.request.urlopen") as urlopen:
        assert _collector()._probe_app_health("nginx") == {}
        urlopen.assert_not_called()


def test_degraded_fields_extracted():
    body = json.dumps({"status": "healthy", "engine_degraded": True, "degraded_reason": "HF auth failed"}).encode(
        "utf-8"
    )
    with patch("slm.agent.health_collector.urllib.request.urlopen", return_value=_fake_response(body)):
        result = _collector()._probe_app_health("autobot-tts-worker")
    assert result == {"engine_degraded": True, "degraded_reason": "HF auth failed"}


def test_healthy_engine_reports_not_degraded():
    body = json.dumps({"engine_degraded": False, "degraded_reason": None}).encode("utf-8")
    with patch("slm.agent.health_collector.urllib.request.urlopen", return_value=_fake_response(body)):
        result = _collector()._probe_app_health("autobot-tts-worker")
    assert result == {"engine_degraded": False, "degraded_reason": None}


def test_missing_field_returns_empty():
    body = json.dumps({"status": "healthy"}).encode("utf-8")
    with patch("slm.agent.health_collector.urllib.request.urlopen", return_value=_fake_response(body)):
        assert _collector()._probe_app_health("autobot-tts-worker") == {}


def test_connection_failure_is_non_fatal():
    with patch(
        "slm.agent.health_collector.urllib.request.urlopen",
        side_effect=OSError("connection refused"),
    ):
        assert _collector()._probe_app_health("autobot-tts-worker") == {}


def test_non_json_body_is_non_fatal():
    with patch(
        "slm.agent.health_collector.urllib.request.urlopen",
        return_value=_fake_response(b"<html>gateway error</html>"),
    ):
        assert _collector()._probe_app_health("autobot-tts-worker") == {}
