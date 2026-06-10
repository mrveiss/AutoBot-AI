# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Backwards-compat shim — canonical implementation is in middleware/.

The ``extensions`` package was renamed to ``middleware`` (#7426). This module
re-exports the public API so legacy ``extensions.hooks`` imports keep working,
and removes a full-file duplicate (#9794). Remove together with the rest of the
extensions→middleware shim.
"""

from middleware.hooks import HOOK_METADATA, HookPoint, get_hook_metadata

__all__ = ["HookPoint", "HOOK_METADATA", "get_hook_metadata"]
