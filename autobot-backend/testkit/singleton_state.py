# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No test inherits the feature-flag singleton or its read cache from another (#18998).

``get_feature_flags()`` returns a process-wide ``FeatureFlags`` whose enforcement-mode and
per-endpoint reads are cached for ``AUTOBOT_FEATURE_FLAG_CACHE_TTL_SECONDS``. Without a reset, a
value one test stored (or a Redis failure it simulated) is served to the next test for that window.
"""

from __future__ import annotations

import sys

import pytest


def _reset_feature_flags() -> None:
    """Drop the singleton and empty its cache. A no-op until a test has imported the module."""
    module = sys.modules.get("services.feature_flags")
    if module is None:
        return
    flags = getattr(module, "_feature_flags", None)
    if flags is not None:
        flags._cache_invalidate()
    module._feature_flags = None


@pytest.fixture(autouse=True)
def reset_feature_flags_singleton():
    """Fresh ``_feature_flags`` singleton and empty cache before and after every test."""
    _reset_feature_flags()
    yield
    _reset_feature_flags()
