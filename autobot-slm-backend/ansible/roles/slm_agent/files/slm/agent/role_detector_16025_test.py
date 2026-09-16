# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for multi-unit role detection (Issue #16025, AC4).

``RoleDefinition.systemd_service`` became a sequence -- a role can own more
than one systemd unit (e.g. the backend role's autobot-backend +
autobot-celery). A role is only "running" when every one of its units is.
"""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from slm.agent.role_detector import RoleDefinition, RoleDetector


def _detect(systemd_service, running_units):
    """Detect a single-field role with the given units, faking systemctl."""
    role = RoleDefinition(name="x", target_path="", systemd_service=systemd_service)
    detector = RoleDetector()
    with patch.object(RoleDetector, "_check_service", side_effect=lambda unit: unit in running_units):
        return detector._detect_role(role, listening_ports=set())


def test_service_name_lists_every_unit():
    status = _detect(["autobot-backend", "autobot-celery"], running_units={"autobot-backend", "autobot-celery"})
    assert status.service_name == "autobot-backend, autobot-celery"


def test_running_requires_every_unit_to_be_active():
    status = _detect(["autobot-backend", "autobot-celery"], running_units={"autobot-backend"})
    assert status.service_running is False


def test_running_is_true_when_all_units_are_active():
    status = _detect(["autobot-backend", "autobot-celery"], running_units={"autobot-backend", "autobot-celery"})
    assert status.service_running is True


def test_a_single_unit_role_is_unaffected():
    status = _detect(["tigervncserver"], running_units={"tigervncserver"})
    assert status.service_name == "tigervncserver"
    assert status.service_running is True
