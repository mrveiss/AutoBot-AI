# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Re-export shim — canonical home is ``autobot_shared.plugin_sdk.capabilities`` (#11636)."""

from autobot_shared.plugin_sdk.capabilities import (
    CapabilityChecker,
    CapabilityContext,
    CapabilityError,
    PluginCapability,
    TrustTier,
)

__all__ = [
    "PluginCapability",
    "CapabilityChecker",
    "CapabilityContext",
    "CapabilityError",
    "TrustTier",
]
