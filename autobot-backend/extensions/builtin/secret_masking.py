# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Backwards-compat shim — canonical implementation is in middleware/builtin/.

The ``extensions`` package was renamed to ``middleware`` (#7426); the builtin
extensions live under ``middleware/builtin/``. This module re-exports the public
API so the legacy ``extensions.builtin.secret_masking`` import keeps working,
and removes a full-file duplicate that had drifted only by its base import
(#9779). Remove together with the rest of the extensions→middleware shim.
"""

from middleware.builtin.secret_masking import SecretMaskingExtension

__all__ = ["SecretMaskingExtension"]
