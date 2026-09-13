# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The startup error file a failed critical startup leaves for ``/api/health`` (GH#8947).

The process exits before binding its port, so the in-memory app state cannot
report the failure; the file survives and the next (probe) process reads it
(``api/system.py``). Writing is synchronous on purpose: callers inside ``async
def`` run it through ``asyncio.to_thread`` so it never blocks the event loop
(#7444, #16250).
"""

import json

from autobot_shared.ssot_constants import STARTUP_ERROR_FILE
from autobot_shared.time_utils import utc_timestamp


def persist_startup_error(error_type: str) -> None:
    """Record *error_type* and the time in the startup error file."""
    STARTUP_ERROR_FILE.parent.mkdir(parents=True, exist_ok=True)
    STARTUP_ERROR_FILE.write_text(
        json.dumps(
            {
                "error_type": error_type,
                "timestamp": utc_timestamp(),
            }
        ),
        encoding="utf-8",
    )
