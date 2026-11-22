# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The heartbeat's CPU figure is a since-last-beat average (#19292).

A 100 ms ``psutil.cpu_percent(interval=0.1)`` window turned any momentary
burst into the whole beat's CPU figure, and that one sample decided the
node's status. The collector now primes psutil once and reads
``interval=None`` -- the average since the previous read.
"""

from unittest.mock import MagicMock, patch

from slm.agent.health_collector import HealthCollector


def _collect_with(psutil_mock: MagicMock) -> None:
    with (
        patch("slm.agent.health_collector.psutil", psutil_mock),
        patch("slm.agent.health_collector.probe_gpus", return_value=[]),
        patch("slm.agent.health_collector._npu_present", return_value=False),
        patch("slm.agent.health_collector._free_disk_model_dir_mb", return_value=0),
    ):
        collector = HealthCollector(discover_services=False)
        assert psutil_mock.cpu_percent.call_count == 1, "construction must prime the sampler exactly once"
        collector.collect()
        collector.collect()


def test_the_sampler_is_primed_at_construction_and_never_blocks():
    psutil_mock = MagicMock()
    psutil_mock.cpu_percent.return_value = 12.5
    psutil_mock.virtual_memory.return_value = MagicMock(percent=10.0, total=1024 * 1024 * 1024)
    psutil_mock.disk_usage.return_value = MagicMock(percent=10.0)
    psutil_mock.boot_time.return_value = 0

    _collect_with(psutil_mock)

    calls = psutil_mock.cpu_percent.call_args_list
    assert len(calls) == 3, "one prime plus one read per collect()"
    assert all(call.kwargs == {"interval": None} for call in calls), calls


def test_the_heartbeat_reports_the_agents_own_interval():
    """The SLM sizes its self-heartbeat stand-down window from it (#19292 review)."""
    from slm.agent.heartbeat_payload import build_heartbeat_payload

    with patch("slm.agent.heartbeat_payload.get_listening_ports", return_value=[]):
        with_interval = build_heartbeat_payload({}, "Linux", None, MagicMock(), False, heartbeat_interval_s=45)
        without = build_heartbeat_payload({}, "Linux", None, MagicMock(), False)
    assert with_interval["extra_data"]["heartbeat_interval_s"] == 45
    assert "heartbeat_interval_s" not in without["extra_data"]
