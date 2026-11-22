# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#19372: the backend service registry honours AUTOBOT_DEPLOYMENT_MODE.

It used to ask the ConfigManager for the flat key ``"deployment.mode"``, which never exists, so
the variable never reached it and the registry always auto-detected.
"""

from __future__ import annotations

import logging
import os
from unittest.mock import patch

from autobot_shared.service_registry_core import DeploymentMode
from utils.service_registry import ServiceRegistry


def _detected(environ: dict) -> DeploymentMode:
    registry = ServiceRegistry.__new__(ServiceRegistry)  # only the mode decision is under test
    registry.logger = logging.getLogger(__name__)
    with patch.dict(os.environ, environ, clear=True), patch("os.path.exists", return_value=False):
        return registry._detect_deployment_mode()


def test_a_set_mode_wins() -> None:
    assert _detected({"AUTOBOT_DEPLOYMENT_MODE": "distributed"}) is DeploymentMode.DISTRIBUTED


def test_an_unset_mode_is_detected() -> None:
    assert _detected({}) is DeploymentMode.LOCAL
