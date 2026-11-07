# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Rolling chat-history summary AUTOBOT_* registrations (#20852).

A sibling of ``env_registry_chat_attachments`` (which imports this module, because
``env_registry.py`` is closed to new entries); the contract is ``env_registry``'s.
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_ROLLING_SUMMARY_RECENT_TURNS",
        type=int,
        default=2,
        description="Chat turns kept verbatim in the prompt; older turns are folded into a rolling summary.",
        component="chat",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_ROLLING_SUMMARY_TTL_SECONDS",
        type=int,
        default=3600,
        description="Age after which a cached rolling chat summary is rebuilt from the turns.",
        component="chat",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_ROLLING_SUMMARY_FAILURE_BACKOFF_SECONDS",
        type=int,
        default=300,
        description="Quiet period after a failed rolling-summary attempt before another is made.",
        component="chat",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_ROLLING_SUMMARY_MAX_TOKENS",
        type=int,
        default=500,
        description="Output token cap for the rolling chat summary.",
        component="chat",
    )
)
