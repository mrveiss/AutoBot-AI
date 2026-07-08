# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Resource visibility scope, mirroring SecretScope (#11277). Authorization only."""

from enum import Enum


class ScopeLevel(str, Enum):
    """Visibility scope for a shareable resource (skill or agent)."""

    USER = "user"
    SESSION = "session"
    SHARED = "shared"
    GROUP = "group"
    ORGANIZATION = "organization"

    @classmethod
    def default(cls) -> "ScopeLevel":
        """Default scope for new resources: company-wide."""
        return cls.ORGANIZATION
