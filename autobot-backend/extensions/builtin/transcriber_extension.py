# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Backwards-compat shim — canonical implementation is in middleware/builtin/.

The ``extensions`` package was renamed to ``middleware`` (#7426); the builtin
extensions live under ``middleware/builtin/``. This module re-exports the public
API so the legacy ``extensions.builtin.transcriber_extension`` import keeps
working, and removes a full-file duplicate (#9794). The module-level ``router``
is re-exported because feature_routers.py fetches it via ``getattr``. Remove
together with the rest of the extensions→middleware shim.
"""

from middleware.builtin.transcriber_extension import (
    TranscriberExtension,
    get_transcriber_router,
    router,
)

__all__ = ["TranscriberExtension", "get_transcriber_router", "router"]
