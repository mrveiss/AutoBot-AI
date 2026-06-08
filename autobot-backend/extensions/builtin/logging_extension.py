# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Backwards-compat shim — canonical implementation is in middleware/builtin/.

The ``extensions`` package was renamed to ``middleware`` (#7426); the builtin
extensions live under ``middleware/builtin/``. This module re-exports the public
API so the legacy ``extensions.builtin.logging_extension`` import keeps working,
and removes a full-file duplicate that had drifted only by its base import
(#9779). Remove together with the rest of the extensions→middleware shim.
"""

from middleware.builtin.logging_extension import LoggingExtension

__all__ = ["LoggingExtension"]
