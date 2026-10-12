# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Security AUTOBOT_* environment variable registrations.

Split out of ``env_registry.py`` rather than added inline, for the reason that
file's own docstring gives: a new variable goes in an
``env_registry_<component>.py`` sibling. The mechanical reason is the one
``env_registry_logging.py`` records — ``env_registry.py`` sits at its
grandfathered file-size ceiling (#14236) with no slack, and the ratchet forbids
raising a ceiling to make room, so an inline registration cannot land there at
all.

#13602 added the first ``component="security"`` variable, so this is the
component's first home rather than a move of existing entries.

Registration contract (import side effect, ordering): see ``env_registry`` (#16415).
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_LOG_VALUE_MAX_CHARS",
        type=int,
        default=256,
        description=(
            "Longest untrusted value sanitize_log_value() will interpolate into a log line "
            "(#13602). Beyond it the value is truncated with an explicit marker, so the "
            "subject of a rejected request cannot pad the log store out. A negative value is "
            "rejected in favour of the default: disabling the bound would defeat the guard."
        ),
        component="security",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_EGRESS_INTERNAL_ORIGINS_TTL_S",
        type=int,
        default=60,
        description=(
            "Seconds the egress policy reuses the origins returned by registered internal-origin "
            "providers (e.g. SLM-managed nodes) before asking them again (#17576). Static origins "
            "from the SSOT are never cached. A provider that raises is logged and skipped."
        ),
        component="security",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_EXECUTION_MEMORY_LIMIT",
        type=str,
        default="512m",
        description=(
            "Memory cap (Docker memory string) for pooled and snapshot-restored execution "
            "containers; swap is capped at the same value, so there is no swap (#17267). "
            "Cold-start tasks size their own cap from the task's resource limits. Raising it "
            "lets warm-pool code use more memory before the kernel OOM-kills it "
            "(autobot_shared/container_hardening.py)."
        ),
        component="security",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_EGRESS_PROVIDER_TIMEOUT_S",
        type=int,
        default=5,
        description=(
            "Seconds one internal-origin provider may run before it is abandoned for this refresh "
            "(#17576). A provider that times out or raises is logged and skipped; the static SSOT "
            "origins still apply."
        ),
        component="security",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_EXECUTION_TMPFS_SIZE",
        type=str,
        default="64m",
        description=(
            "Size of the scratch tmpfs (mounted noexec,nosuid at the container scratch path) "
            "that a read-only execution container writes to (#17267). Raising it lets code "
            "stage larger temporary files; lowering it fails writes sooner "
            "(autobot_shared/container_hardening.py)."
        ),
        component="security",
    )
)
