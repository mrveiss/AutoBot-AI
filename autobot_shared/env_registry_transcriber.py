# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Transcriber AUTOBOT_* environment variable registrations.

Split out of ``env_registry.py``, which sits at its grandfathered file-size ceiling.
Imported by ``env_registry`` itself, so registration happens whenever it loads.
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_TRANSCRIBER_DB_PATH",
        type=str,
        default="data/transcriber.db",
        description=(
            "SQLite database backing the transcriber. Relative to the working "
            "directory unless given as an absolute path."
        ),
        component="voice",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_TRANSCRIBER_PROGRESS_POLL_S",
        type=float,
        default=1.0,
        description="Seconds between status polls on the transcriber recording progress SSE stream.",
        component="voice",
        range=(0.1, 60.0),
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_TRANSCRIBER_PROGRESS_MAX_S",
        type=float,
        default=3600.0,
        description="Maximum seconds a transcriber recording progress SSE stream stays open.",
        component="voice",
        range=(1.0, 86400.0),
    )
)
