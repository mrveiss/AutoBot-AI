# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The agent's heartbeat carries its GPU probe to the SLM (#16280).

The SLM stores ``extra_data`` on the node as-is, so the three GPU states the UI
shows (#15226) are decided here: an absent key, ``[]``, or a device list.
"""

from unittest.mock import MagicMock, patch

from slm.agent.health_collector import HealthCollector
from slm.agent.heartbeat_payload import build_heartbeat_payload

DEVICE = {"device_type": "nvidia-gpu", "index": 0, "name": "NVIDIA GeForce RTX 4070 Laptop GPU", "monitored": True}


def _payload(health: dict) -> dict:
    with patch("slm.agent.heartbeat_payload.get_listening_ports", return_value=[]):
        return build_heartbeat_payload(health, "Linux", None, MagicMock(), definitions_loaded=False)


def test_collect_reports_the_gpu_probe():
    with patch("slm.agent.health_collector.probe_gpus", return_value=[DEVICE]) as probe:
        health = HealthCollector(discover_services=False).collect()

    probe.assert_called_once_with()
    assert health["gpu"] == [DEVICE]


def test_the_payload_forwards_the_devices_in_extra_data():
    assert _payload({"gpu": [DEVICE]})["extra_data"]["gpu"] == [DEVICE]


def test_the_payload_forwards_an_empty_probe_as_none_present():
    assert _payload({"gpu": []})["extra_data"]["gpu"] == []


def test_the_payload_omits_the_key_when_nothing_was_probed():
    assert "gpu" not in _payload({})["extra_data"]
