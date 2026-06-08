# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Redis TTL and async timeout constants (all values in seconds).

MIGRATION (Issue #GH7440):
    This module re-exports from autobot_shared.ssot_constants for backward compatibility.
    Import directly from autobot_shared.ssot_constants for new code.
"""

from autobot_shared.ssot_constants import (  # noqa: F401,F403
    TIMEOUT_HTTP_DEFAULT,
    TIMEOUT_HTTP_LONG,
    TIMEOUT_TASK_ANALYSIS,
    TTL_1_HOUR,
    TTL_5_MINUTES,
    TTL_7_DAYS,
    TTL_10_SECONDS,
    TTL_24_HOURS,
    TTL_30_DAYS,
    TTL_90_DAYS,
    TTL_365_DAYS,
    TTL_WORKING_MEMORY_DEFAULT,
)
