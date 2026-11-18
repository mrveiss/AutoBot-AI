# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Response model of the fleet-wide start/stop/restart routes (#18714).

A subclass of ``ServiceActionResponse`` rather than a field on it: ``models/schemas.py`` is a
grandfathered file that may not grow, and only the fleet routes carry per-node diagnostics.
Every field of the parent is unchanged, so existing consumers read the response as before.
"""

from models.schemas import ServiceActionResponse


class FleetServiceActionResponse(ServiceActionResponse):
    """``ServiceActionResponse`` for an action applied across the fleet."""

    #: node_id -> ``systemctl status`` + journal text, for each node where the action failed.
    #: None on success. A node's entry is bounded (``AUTOBOT_SLM_FAILURE_DIAG_MAX_CHARS`` per section).
    diagnostics: dict[str, str] | None = None
