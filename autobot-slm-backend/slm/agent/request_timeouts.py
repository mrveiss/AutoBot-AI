# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Total request timeouts for the agent's admin-server POSTs (#19461).

aiohttp raises ``TimeoutError`` (not a ``ClientError``) when these fire, so the
callers treat it as a missed heartbeat / failed sync. A real cancellation is a
``BaseException`` and still propagates. 0, NaN, inf and negatives fall back to
the default: aiohttp treats 0 and NaN as "no timer", the hang this prevents.
"""

from autobot_shared.env_utils import env_float_clamped

HEARTBEAT_TIMEOUT_SECONDS = env_float_clamped("SLM_HEARTBEAT_TIMEOUT", 10.0, positive_finite=True)
EVENT_SYNC_TIMEOUT_SECONDS = env_float_clamped("SLM_EVENT_SYNC_TIMEOUT", 30.0, positive_finite=True)
