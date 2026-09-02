# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Secrets response shapes that ``models/schemas.py`` has no room for (#13139).

Its own module for the reason ``models/schemas_health.py`` records:
``models/schemas.py`` sits at its recorded size ceiling and a grandfathered
file may not grow (#14236), so a response model that has to exist somewhere
gets a sibling module rather than a shaved docstring elsewhere.
"""

from __future__ import annotations

from pydantic import BaseModel


class DependentRolesResponse(BaseModel):
    """Secret key to dependent-role mapping used by the apply-secrets action."""

    mapping: dict[str, list[str]]
