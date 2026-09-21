# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Response model for the honesty-fixed ``POST /system/emergency-stop`` (#16843).

A companion ``schemas_<domain>.py``: the no-local-schemas hook (#6056) rejects
a router that defines its own ``BaseModel``. Extends the existing
``AdvancedControlEmergencyStopResponse`` rather than editing it in place --
``schemas_workflows.py`` is a grandfathered ratchet file already at its
line-count ceiling (#14236: an exemption freezes the size it was granted, it
does not license more).
"""

from __future__ import annotations

from typing import List

from api.schemas_workflows import AdvancedControlEmergencyStopResponse


class EmergencyStopReportResponse(AdvancedControlEmergencyStopResponse):
    """Reports which tasks were actually found and registered for pause."""

    tasks_paused: List[str]
    durable: bool
    """False when the pause was only recorded in-process (Redis unavailable)."""
