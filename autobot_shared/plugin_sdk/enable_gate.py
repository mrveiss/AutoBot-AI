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

from pathlib import Path
from typing import List, Mapping, Protocol

from .base import PluginManifest


class EnableGate(Protocol):
    """Names the discovered plugins that may be imported."""

    async def admit(self, manifests: List[PluginManifest], locations: Mapping[str, Path]) -> List[PluginManifest]:
        """Return the subset of *manifests* an operator has enabled.

        *locations* maps a plugin name to its directory on disk, for a gate that needs to look at the files.
        """

    async def still_admitted(self, plugin_name: str) -> bool:
        """Whether *plugin_name* may still be imported and enabled; an operator can disable it after admission."""
