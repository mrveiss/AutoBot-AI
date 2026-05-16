# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
ExtensionManifest dataclass (GH#7369).

Deliberately minimal — no service or framework imports so this module can
be imported without triggering the full extensions package initialization.
"""

from dataclasses import dataclass


@dataclass
class ExtensionManifest:
    """Manifest metadata for an Extension, derived from class-level attributes.

    Satisfies ManifestContract structurally; no Pydantic dependency.
    Canonical location: autobot_shared/plugin_sdk/extension_manifest.py
    """

    name: str
    version: str
    description: str
    kind: str = "extension"
    """Manifest metadata for an Extension, derived from class-level attributes.

    Satisfies ManifestContract structurally; no Pydantic dependency.
    """

    name: str
    version: str
    description: str
    kind: str = "extension"
