# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The decision that lets a plugin's code run in this process (#17421).

Discovery reads manifests only. Importing a plugin executes its code, so the
host asks an :class:`EnableGate` which of the discovered plugins an operator has
enabled and imports only those. The durable record lives with the host (the
backend keeps it in the database); the SDK only states the contract.
"""

from typing import List, Protocol

from .base import PluginManifest


class EnableGate(Protocol):
    """Names the discovered plugins that may be imported."""

    async def admit(self, manifests: List[PluginManifest]) -> List[PluginManifest]:
        """Return the subset of *manifests* an operator has enabled."""
