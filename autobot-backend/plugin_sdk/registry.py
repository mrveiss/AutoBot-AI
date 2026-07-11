# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Re-export shim — canonical home is ``autobot_shared.plugin_sdk.registry`` (#11637)."""

from autobot_shared.plugin_sdk.registry import Registry, get_registry

__all__ = ["Registry", "get_registry"]
