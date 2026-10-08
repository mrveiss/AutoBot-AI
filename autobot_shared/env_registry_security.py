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
