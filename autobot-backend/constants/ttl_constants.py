# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Redis TTL and async timeout constants (all values in seconds).

Issue #3529: Centralized TTL/timeout constants to replace raw integer
literals across the codebase, eliminating magic numbers in Redis expire
calls and async task timeouts.
"""

# Redis TTL values
TTL_1_HOUR = 3_600
TTL_24_HOURS = 86_400
TTL_7_DAYS = 86_400 * 7
TTL_30_DAYS = 86_400 * 30
TTL_90_DAYS = 86_400 * 90

# HTTP / async task timeouts
TIMEOUT_HTTP_DEFAULT = 60
TIMEOUT_HTTP_LONG = 120
TIMEOUT_TASK_ANALYSIS = 1_800
