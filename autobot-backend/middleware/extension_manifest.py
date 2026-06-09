# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Re-export ExtensionManifest from canonical location in autobot_shared."""

from autobot_shared.plugin_sdk.extension_manifest import ExtensionManifest

__all__ = ["ExtensionManifest"]
