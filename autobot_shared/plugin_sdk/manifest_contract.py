# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
ManifestContract Protocol (GH#7369)

Structural protocol that plugin, skill, and extension manifests must satisfy
for participation in the UnifiedRegistry.
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
