# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Re-export shim — canonical home is ``autobot_shared.plugin_sdk.hooks`` (#11636).

The old backend fork never shipped ``hooks.py``, so core plugins importing
``plugin_sdk.hooks`` (logger-plugin, kb-event-plugin) failed to load via the
bare path. The shim closes that gap.
"""

from autobot_shared.plugin_sdk.hooks import (
    HOOK_REGISTRY,
    Hook,
    HookRegistry,
    HookSignature,
    validate_hook_names,
)

__all__ = [
    "HOOK_REGISTRY",
    "Hook",
    "HookRegistry",
    "HookSignature",
    "validate_hook_names",
]
