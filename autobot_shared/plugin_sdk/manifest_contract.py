# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
ManifestContract Protocol (GH#7369)

Structural protocol that plugin, skill, and extension manifests must satisfy
for participation in the Registry.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class ManifestContract(Protocol):
    """Structural protocol for all manifest types.

    Plugins (PluginManifest), skills (manifest dict wrapper), and extensions
    (ExtensionManifest) all satisfy this protocol structurally — no changes to
    their inheritance chains are required.
    """

    name: str
    version: str
    description: str
    kind: str  # "plugin" | "skill" | "extension"
