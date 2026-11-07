# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Where a stored plan lives in Redis, and for how long (#21023).

A chat turn scopes its plans by session id (``autobot:plans:<session>:<id>``), so one session cannot read
another's plan; an empty scope keeps the legacy unscoped key ``autobot:plans:<id>``.
"""

from __future__ import annotations

from autobot_shared.env_utils import env_int
from constants.threshold_constants import TimingConstants

#: Seconds a stored plan lives in Redis. Env-backed so retention is not a deploy-time literal.
PLAN_TTL_SECONDS: int = env_int("AUTOBOT_PLAN_TTL_SECONDS", default=TimingConstants.HOURLY_INTERVAL * 24)


def plan_key(scope: str, plan_id: str) -> str:
    """The Redis key for ``plan_id`` under ``scope`` (a session id; empty = unscoped)."""
    return f"autobot:plans:{scope}:{plan_id}" if scope else f"autobot:plans:{plan_id}"
