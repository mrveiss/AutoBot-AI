# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Agent-ledger AUTOBOT_* environment variable registrations (#18391).

A sibling of ``env_registry_agent_runtime`` (which imports this module, because
it sits at the file-size ceiling and ``env_registry.py`` is closed to new
entries); the registration contract is the one ``env_registry`` states (#16415).
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_LEDGER_EVENT_CAP",
        type=int,
        default=500,
        description=(
            "How many coordination events the agent ledger retains, newest first (#18391): claims that "
            "expired while held, releases aimed at another holder's claim, and yield requests with "
            "their answers. A bounded audit trail for the ledger screens, not an archive."
        ),
        component="orchestration",
        range=(50, 5000),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_LEDGER_EVENT_TTL_S",
        type=int,
        default=604800,
        description=(
            "Idle lifetime of the agent ledger's event list, refreshed by every write (#18391). "
            "Nothing is aged out individually: only the event cap trims the list, and this TTL "
            "(reset on every write) only stops an abandoned list outliving the install."
        ),
        component="orchestration",
        range=(3600, 7776000),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_LEDGER_TEXT_CAP",
        type=int,
        default=280,
        description=(
            "Longest caller-supplied free text (a yield request's reason) an agent-ledger event keeps (#18391). "
            "The activity screen shows it to other viewers, so it is bounded on write."
        ),
        component="orchestration",
        range=(32, 2000),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_LEDGER_PROJECTION_TTL_S",
        type=int,
        default=120,
        description=(
            "How long the user backend's snapshot of live agent state (presence, pending peer "
            "messages, idle subscriptions) stays readable by the SLM ledger without a refresh "
            "(#18632). Longer than the presence sweep so one slow sweep does not blank the SLM; "
            "a stopped backend's snapshot expires and reads as 'couldn't read', never as stale."
        ),
        component="orchestration",
        range=(10, 3600),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_LEDGER_SCOPE_MAX_LEN",
        type=int,
        default=512,
        description=(
            "Longest claim scope a yield request may name (#18607). A longer request body is "
            "refused with HTTP 422 at parse time, before anything reads it."
        ),
        component="orchestration",
        range=(64, 4096),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_LEDGER_ID_MAX_LEN",
        type=int,
        default=256,
        description=(
            "Longest holder task id a yield request may name (#18607). A longer request body is "
            "refused with HTTP 422 at parse time, before anything reads it."
        ),
        component="orchestration",
        range=(32, 1024),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_LEDGER_YIELD_ASK_WINDOW_S",
        type=int,
        default=60,
        description=(
            "Seconds over which one person may ask the holder of one claim to release it at most "
            "AUTOBOT_LEDGER_YIELD_ASK_LIMIT times (#18599). Keyed by user and scope."
        ),
        component="orchestration",
        range=(1, 86400),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_LEDGER_YIELD_ASK_LIMIT",
        type=int,
        default=1,
        description=(
            "How many times one person may ask the holder of one claim to release it inside "
            "AUTOBOT_LEDGER_YIELD_ASK_WINDOW_S (#18599); further asks answer HTTP 429."
        ),
        component="orchestration",
        range=(1, 100),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_ISSUE_CLAIM_SESSION_TTL_S",
        type=int,
        default=14400,
        description=(
            "How long a developer session's claim on a GitHub issue survives without a ledger "
            "heartbeat (#17098). The session ledger writes through to the work-claims registry "
            "for its issue kind; a crashed session frees the issue after this long. Mirrors the "
            "ledger's own 4h default."
        ),
        component="orchestration",
        range=(60, 172800),
    )
)


# --- issue-claims CLI API transport (#18811): the session ledger reaches the registry via AutoBot's API ---

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_ISSUE_CLAIMS_API_URL",
        type=str,
        default="",
        description=(
            "Base URL of AutoBot's backend for the issue-claims CLI (#18811). When set, "
            "`python -m autobot_shared.coordination.issue_claims` talks to /api/coordination/issue-claims "
            "instead of Redis, so a developer checkout needs no registry credential. Must be https, or http "
            "to a loopback host. Authenticate once with `issue_claims login` (credential kept in the kernel "
            "keyring, cleared on reboot). Never derived from the SSOT backend URL. Unset keeps the direct "
            "Redis transport."
        ),
        component="orchestration",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_ISSUE_CLAIMS_CREDENTIAL_TTL_S",
        type=int,
        default=604800,
        description=(
            "Lifetime of an issue-claims client credential minted by `issue_claims login` (#18811). The "
            "credential is a secret in the minting user's vault; past this age it is refused, so one "
            "orphaned by a reboot (the kernel keyring is cleared) stops working without a revoke."
        ),
        component="orchestration",
        range=(3600, 7776000),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_ISSUE_CLAIMS_API_TIMEOUT_S",
        type=int,
        default=10,
        description="Per-request timeout of the issue-claims CLI's API transport; expiry fails closed (#18811).",
        component="orchestration",
        range=(1, 120),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_ISSUE_CLAIMS_FAILURE_WINDOW_S",
        type=int,
        default=300,
        description=(
            "Window over which failed issue-claims credential checks are counted per client source and "
            "aggregated into one audit event (#18811)."
        ),
        component="orchestration",
        range=(10, 86400),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_ISSUE_CLAIMS_FAILURE_LIMIT",
        type=int,
        default=10,
        description=(
            "Failed issue-claims credential checks one client source may make per window; past it the "
            "source is refused with 429 before any credential lookup (#18811)."
        ),
        component="orchestration",
        range=(1, 10000),
    )
)
