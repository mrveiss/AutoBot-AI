# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Coverage for the ``category`` default in
``ErrorBoundaryManager._calculate_error_groupings`` (#14047)."""

from unittest.mock import MagicMock

from autobot_shared.error_boundaries.boundary_manager import ErrorBoundaryManager
from autobot_shared.ssot_constants import CategoryDefaults


def test_missing_category_defaults_to_unknown():
    manager = ErrorBoundaryManager(redis_client=MagicMock())

    categories, _severities, _components = manager._calculate_error_groupings([{}])

    assert categories == {CategoryDefaults.UNKNOWN: 1}


def test_explicit_category_overrides_default():
    manager = ErrorBoundaryManager(redis_client=MagicMock())

    categories, _severities, _components = manager._calculate_error_groupings([{"category": "network"}])

    assert categories == {"network": 1}
    assert CategoryDefaults.UNKNOWN not in categories
