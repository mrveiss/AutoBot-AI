# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Register the API process's serving loop with everything that must reach it (#20887)."""

from __future__ import annotations

import asyncio

from autobot_shared.async_compat import register_main_loop
from middleware.audit_middleware import set_main_event_loop


def register_main_loops(loop: asyncio.AbstractEventLoop) -> None:
    """Record ``loop`` for sync-endpoint audit scheduling and for ``run_or_schedule``.

    Called once from the lifespan, inside the running loop, before serving.
    """
    set_main_event_loop(loop)
    register_main_loop(loop)
