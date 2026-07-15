# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Re-export shim — canonical home is ``autobot_shared.plugin_sdk.capabilities`` (#11636)."""

from autobot_shared.plugin_sdk.capabilities import (
    Capability,
    CapabilityChecker,
    CapabilityContext,
    CapabilityError,
    TrustTier,
)

__all__ = [
    "Capability",
    "CapabilityChecker",
    "CapabilityContext",
    "CapabilityError",
    "TrustTier",
]
