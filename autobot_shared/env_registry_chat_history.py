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
        default=86400,
        description=(
            "Redis lifetime of a session's rolling chat summary. Kept longer than the rebuild age (raised to twice "
            "AUTOBOT_ROLLING_SUMMARY_REBUILD_AGE_SECONDS if set lower), so a stale summary still serves the prompt "
            "while the background rebuild runs. Only a session with no key (a brand-new worker or a session "
            "idle past this) gets no summary on its first turn."
        ),
        component="chat",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_ROLLING_SUMMARY_REBUILD_AGE_SECONDS",
        type=int,
        default=3600,
        description=(
            "Age of a rolling chat summary since its last rebuild from the durable chat history, past which the next "
            "refresh rebuilds it instead of extending it (bounds drift from folding a summary into a summary)."
        ),
        component="chat",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_ROLLING_SUMMARY_FAILURE_BACKOFF_SECONDS",
        type=int,
        default=300,
        description=("Quiet period after a failed rolling-summary attempt before another is made."),
        component="chat",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_ROLLING_SUMMARY_LOCK_MARGIN_SECONDS",
        type=int,
        default=30,
        description=(
            "Seconds added to one summariser call's timeout to make the per-session refresh lock lifetime. The lock is "
            "renewed before each chunk, and the summary write is refused if the lock was lost, so a crashed refresh "
            "blocks the next one for at most this long plus one summariser timeout."
        ),
        component="chat",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_ROLLING_SUMMARY_CHUNK_TURNS",
        type=int,
        default=10,
        description=(
            "Chat turns folded into the rolling summary per summariser call group; a rebuild folds from the OLDEST "
            "turn in chunks of this size, so none is truncated."
        ),
        component="chat",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_ROLLING_SUMMARY_MAX_CHUNKS",
        type=int,
        default=20,
        description=(
            "Cost ceiling: most chunks one rolling-summary refresh folds. When a rebuild needs more, a warning is "
            "logged and the remaining (newest) turns are folded by the following refreshes; no turn is dropped."
        ),
        component="chat",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHAT_KNOWLEDGE_MAX_CHUNKS",
        type=int,
        default=4,
        description=(
            "Most summariser chunks (of AUTOBOT_SUMMARIZER_INPUT_MAX_CHARS characters) a chat-to-knowledge "
            "transcript may need; a longer chat is refused with an error instead of costing unbounded LLM calls."
        ),
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
