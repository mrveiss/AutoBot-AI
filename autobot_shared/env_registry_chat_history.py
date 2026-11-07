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
        description=(
            "Redis lifetime of a session's rolling chat summary; past it, or this age since its last "
            "rebuild, it is rebuilt from the durable chat history."
        ),
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
        name="AUTOBOT_ROLLING_SUMMARY_LOCK_TTL_SECONDS",
        type=int,
        default=120,
        description=(
            "Seconds a per-session rolling-summary refresh lock is held before it expires; a crashed "
            "refresh blocks the next one this long."
        ),
        component="chat",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_ROLLING_SUMMARY_REBUILD_MAX_TURNS",
        type=int,
        default=200,
        description="Most recent durable chat turns read when a rolling summary is rebuilt from the chat history.",
        component="chat",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SUMMARIZER_DEFAULT_MAX_TOKENS",
        type=int,
        default=500,
        description=(
            "Output token cap, and the length the prompt asks for, for every conversation summary that "
            "names no other (rolling summary, compact hook, overflow protection, /chat/summarize)."
        ),
        component="chat",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SUMMARIZER_INPUT_MAX_CHARS",
        type=int,
        default=24000,
        description=(
            "Conversation characters sent to the summariser in one call; longer input is summarised in " "chunks."
        ),
        component="chat",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SUMMARIZER_TIMEOUT_SECONDS",
        type=float,
        default=60.0,
        description=(
            "Seconds one summariser LLM call may take before it is abandoned and counted as a " "summarisation failure."
        ),
        component="chat",
    )
)
