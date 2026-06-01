# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Consolidated voice bundle constants and schemas (GH#9048).

This module serves as the single source of truth for voice bundle definitions,
replacing duplicate constants previously scattered across voice_bundle_user.py
and voice_bundle_admin.py.
"""

from typing import Optional

from pydantic import BaseModel

from api.redis_mcp.rbac import VALID_BUNDLES as _VALID_BUNDLES

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Re-export VALID_BUNDLES from rbac.py as the canonical source
VALID_BUNDLES: frozenset[str] = _VALID_BUNDLES

# Bundle metadata: human-readable labels and descriptions
BUNDLE_DEFINITIONS: dict[str, dict[str, str]] = {
    "voice_safe": {
        "label": "Voice Safe",
        "description": "Basic voice commands for standard users",
    },
    "voice_extended": {
        "label": "Voice Extended",
        "description": "Extended voice commands with advanced features",
    },
    "voice_admin": {
        "label": "Voice Admin",
        "description": "Full voice command set for administrators",
    },
}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class BundleAssignRequest(BaseModel):
    """Request to assign or clear a bundle for a user."""

    bundle_name: Optional[str] = None  # None = clear override
