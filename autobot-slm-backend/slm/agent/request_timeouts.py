# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Total request timeouts for the agent's admin-server POSTs (#19461).

aiohttp raises ``TimeoutError`` (not a ``ClientError``) when these fire, so the
callers treat it as a missed heartbeat / failed sync. A real cancellation is a
``BaseException`` and still propagates.
"""

from autobot_shared.env_utils import env_float

HEARTBEAT_TIMEOUT_SECONDS = env_float("SLM_HEARTBEAT_TIMEOUT", 10.0)
EVENT_SYNC_TIMEOUT_SECONDS = env_float("SLM_EVENT_SYNC_TIMEOUT", 30.0)
