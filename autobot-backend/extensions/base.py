# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Backwards-compat shim — canonical implementation is in middleware/.

The ``extensions`` package was renamed to ``middleware`` (#7426). This module
re-exports the public API so legacy ``extensions.base`` imports keep working,
and removes a full-file duplicate (#9794). ``ExtensionManifest`` is re-exported
so ``from extensions.base import ExtensionManifest`` still works. Remove together
with the rest of the extensions→middleware shim.
"""

from middleware.base import Extension, ExtensionManifest, HookContext

__all__ = ["ExtensionManifest", "Extension", "HookContext"]
