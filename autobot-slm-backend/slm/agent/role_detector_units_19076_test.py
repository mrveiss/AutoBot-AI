# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
A role whose units the node does not have is not installed (Issue #19076).

Service-only roles (``target_path: ""``) had no path to disprove them, so a
missing unit read as "inactive" -- which ``_detected_role_names`` counts as
present -- and every node detected redis, slm-database and slm-monitoring.
"""

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from slm.agent.role_detector import RoleDefinition, RoleDetector


def _status(target_path, installed_units, running_units, units=("redis-stack-server",)):
    role = RoleDefinition(name="x", target_path=target_path, systemd_service=list(units))
    detector = RoleDetector()
    with (
        patch.object(RoleDetector, "_check_service", side_effect=lambda u: u in running_units),
        patch.object(RoleDetector, "_unit_installed", side_effect=lambda u: u in installed_units),
    ):
        return detector._detect_role(role, listening_ports=set()).status


@pytest.mark.parametrize(
    ("installed", "running", "expected"),
    [
        (set(), set(), "not_installed"),
        ({"redis-stack-server"}, set(), "inactive"),
        ({"redis-stack-server"}, {"redis-stack-server"}, "active"),
    ],
    ids=["unit-not-found", "loaded-stopped", "loaded-running"],
)
def test_service_only_role_status_follows_the_unit(installed, running, expected):
    assert _status("", installed, running) == expected


def test_an_existing_path_does_not_make_a_missing_unit_present(tmp_path):
    assert _status(str(tmp_path), set(), set(), units=("autobot-backend",)) == "not_installed"


def test_one_installed_unit_of_several_is_enough_to_be_present():
    units = ("autobot-backend", "autobot-celery")
    assert _status("", {"autobot-backend"}, set(), units=units) == "inactive"


def test_a_path_only_role_keeps_the_path_rule(tmp_path):
    role = RoleDefinition(name="lib", target_path=str(tmp_path), systemd_service=None)
    assert RoleDetector()._detect_role(role, listening_ports=set()).status == "active"
    gone = RoleDefinition(name="lib", target_path=str(tmp_path / "absent"), systemd_service=None)
    assert RoleDetector()._detect_role(gone, listening_ports=set()).status == "not_installed"


@pytest.mark.parametrize(
    ("stdout", "rc", "expected"),
    [("loaded\n", 0, True), ("masked\n", 0, True), ("not-found\n", 0, False), ("", 0, False), ("loaded\n", 1, False)],
    ids=["loaded", "masked", "not-found", "empty", "nonzero-rc"],
)
def test_unit_installed_reads_load_state(stdout, rc, expected):
    fake = SimpleNamespace(stdout=stdout, returncode=rc)
    with patch("slm.agent.role_detector.subprocess.run", return_value=fake) as run:
        assert RoleDetector()._unit_installed("redis-stack-server") is expected
    assert run.call_args.args[0] == ["systemctl", "show", "--property=LoadState", "--value", "redis-stack-server"]


def test_a_failed_unit_probe_adds_nothing():
    with patch("slm.agent.role_detector.subprocess.run", side_effect=subprocess.TimeoutExpired("systemctl", 5)):
        assert RoleDetector()._unit_installed("redis-stack-server") is False
