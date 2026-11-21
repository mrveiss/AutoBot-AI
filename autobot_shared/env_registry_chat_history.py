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
            "renewed before EACH summariser gateway call, and the summary write is refused if the lock was lost, so a "
            "crashed refresh blocks the next one for at most this long plus one summariser timeout."
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
            "turn in chunks of this size, storing the progress after each chunk, so none is dropped."
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
            "Most summariser calls (each of at most AUTOBOT_SUMMARIZER_INPUT_MAX_CHARS characters) a chat-to-knowledge "
            "transcript may need, counted exactly by the summariser before the first call; a longer chat is refused "
            "with an error instead of costing unbounded LLM calls."
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
            "Conversation characters sent to the summariser in one call; longer input is summarised in chunks. A "
            "single message longer than this is split across calls, never cut: every character is summarised."
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

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_CHAT_OWNER_INDEX_COMPLETE_TTL",
        type=int,
        default=86400,
        range=(1, 2591999),
        description=(
            "Seconds the per-user marker that says the chat owner index is complete lives; without it the "
            "index is rebuilt from the session files (security/session_owner_index.py, #21664). Kept below "
            "the 30-day index TTL so the marker never outlives the index."
        ),
        component="chat",
    )
)

# --- chat share adoption (#18890) ---

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SESSION_SHARE_ADOPT_LOCK_TTL_MS",
        type=int,
        default=60000,
        description=(
            "How long one worker may hold the lock while it copies pre-table Redis chat shares into the "
            "durable table (#18890). A crashed holder frees it after this long."
        ),
        component="security",
        range=(1000, 600000),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_SESSION_SHARE_ADOPT_WAIT_SECONDS",
        type=int,
        default=30,
        description=(
            "How long a worker that lost the adoption lock waits for the other to finish before an unshare "
            "fails closed (#18890)."
        ),
        component="security",
        range=(0, 600),
    )
)
