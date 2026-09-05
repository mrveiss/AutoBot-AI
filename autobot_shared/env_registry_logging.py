# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Logging AUTOBOT_* environment variable registrations.

Split out of ``env_registry.py`` rather than added inline, for the reason
``env_registry_terminal.py`` records: that file sits at its grandfathered
file-size ceiling (#14236) with no slack, and the ratchet forbids raising a
ceiling to make room. #15774 needed four new variables for the log-flood
guard, which no amount of compression fits into zero lines, so the whole
logging component moves here — the three that were already there pay for the
import line this module costs, and the component is more coherent for being
in one place.

Importing this module registers every variable below into
``autobot_shared.env_registry.REGISTRY`` as a side effect, exactly like the
``register_env_var(...)`` calls in ``env_registry.py`` itself. It is imported
from there, after ``EnvVarSpec``/``register_env_var``/``REGISTRY`` are
defined, so nothing ever observes a partially-populated registry.
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_LOGS_BACKUP_DIR",
        type=str,
        default="backup",
        description="Directory where rotated log archives are written.",
        component="logging",
    )
)
register_env_var(
    EnvVarSpec(
        name="AUTOBOT_LOGS_DIR",
        type=str,
        default="logs",
        description="Primary directory for application log files.",
        component="logging",
    )
)
register_env_var(
    EnvVarSpec(
        name="AUTOBOT_LOG_FLOOD_ENABLED",
        type=bool,
        default=True,
        description="Bound how many identical WARNING/ERROR records one call site may emit per window (#15774).",
        component="logging",
    )
)
register_env_var(
    EnvVarSpec(
        name="AUTOBOT_LOG_FLOOD_THRESHOLD",
        type=int,
        default=5,
        description="Records one log call site may emit per flood window before the rest are suppressed.",
        component="logging",
    )
)
register_env_var(
    EnvVarSpec(
        name="AUTOBOT_LOG_FLOOD_WINDOW_SECONDS",
        type=int,
        default=60,
        description="Length of the log-flood suppression window, in seconds.",
        component="logging",
    )
)
register_env_var(
    EnvVarSpec(
        name="AUTOBOT_LOG_FLOOD_MAX_KEYS",
        type=int,
        default=2048,
        description="Maximum distinct call sites tracked by the log-flood guard before least-recent eviction.",
        component="logging",
    )
)
register_env_var(
    EnvVarSpec(
        name="AUTOBOT_LOG_VIEWER_URL",
        type=str,
        default="http://localhost:5341",
        description="Base URL of the Seq (or compatible) structured-log viewer.",
        component="logging",
    )
)
