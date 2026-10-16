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
