# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Coverage for the ``current_mode`` error-path default in
``FeatureFlags.get_rollout_statistics`` (#14047).

Unlike most sites touched in this issue, this literal is not a ``.get(key,
default)`` call — it is the unconditional value reported when statistics
collection raises, so there is no "explicit override" case to test; only
that the fallback value itself is unchanged.
"""

import pytest

from constants.threshold_constants import CategoryDefaults
from services.feature_flags import FeatureFlags


@pytest.mark.asyncio
async def test_error_path_reports_unknown_current_mode():
    flags = FeatureFlags()

    async def _boom():
        raise RuntimeError("redis unavailable")

    flags._get_redis = _boom

    result = await flags.get_rollout_statistics()

    assert result["current_mode"] == CategoryDefaults.UNKNOWN
