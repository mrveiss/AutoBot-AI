# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""AUTOBOT_* registrations for the tamper-evident audit chain (#17219).

A per-component sibling: ``env_registry.py`` and ``env_registry_security.py`` are at their size ceilings.
Registration contract (import side effect, ordering): see ``env_registry`` (#16415).
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_AUDIT_CHAIN_LOCK_TIMEOUT_MS",
        type=int,
        default=5000,
        description=(
            "Milliseconds an audit_logs insert waits for the hash-chain lock before the audit write fails (#17219); "
            "a durable caller then refuses the action rather than hang; read by autobot_shared/audit_chain_writer.py."
        ),
        component="security",
        range=(1, 600000),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_AUDIT_VERIFY_BATCH_SIZE",
        type=int,
        default=1000,
        description=(
            "Rows read per batch while verifying the audit_logs hash chain (#17219); "
            "read by autobot-backend/services/audit/integrity.py."
        ),
        component="security",
        range=(1, 100000),
    )
)
