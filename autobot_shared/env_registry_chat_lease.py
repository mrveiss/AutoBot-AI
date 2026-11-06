# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Env vars for the per-session chat write lease (chat_history/session_lease.py, #20862)."""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHAT_LEASE_TTL_MS",
        type=int,
        default=30000,
        range=(1000, None),
        description=(
            "Lifetime in milliseconds of the per-session Redis lease that serialises writes to a chat "
            "file. The holder renews it while it works, so only a crashed holder makes a waiter sit "
            "out the full lifetime (chat_history/session_lease.py, #20862). Minimum 1000."
        ),
        component="chat",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHAT_LEASE_WAIT_S",
        type=float,
        default=30.0,
        range=(0.1, None),
        description=(
            "Seconds a writer waits for another writer's lease on the same chat session before it "
            "raises an error naming the holder. The save is never written unlocked and never dropped "
            "silently (chat_history/session_lease.py, #20862). Minimum 0.1."
        ),
        component="chat",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHAT_LEASE_POLL_S",
        type=float,
        default=0.05,
        range=(0.001, None),
        description=(
            "Seconds between attempts to take a chat session lease another writer holds "
            "(chat_history/session_lease.py, #20862). Minimum 0.001."
        ),
        component="chat",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHAT_LEASE_REDIS_DB",
        type=str,
        default="main",
        description=(
            "Redis database holding the per-session chat lease keys and their fencing counters "
            "(chat_history/session_lease.py, #20862)."
        ),
        component="chat",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHAT_LEASE_KEY_PREFIX",
        type=str,
        default="autobot:chat:session_lease:",
        description=(
            "Key prefix of the per-session chat lease; the session id is appended "
            "(chat_history/session_lease.py, #20862)."
        ),
        component="chat",
    )
)
