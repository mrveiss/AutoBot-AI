# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Backwards-compat shim — canonical implementations are in middleware/builtin/.

The ``extensions`` package was renamed to ``middleware`` (#7426). This package
re-exports the builtin extensions so legacy ``extensions.builtin`` imports keep
working, and removes a full-file duplicate (#9794). Remove together with the
rest of the extensions→middleware shim.
"""

from middleware.builtin import (
    LoggingExtension,
    PermissionEnforcementExtension,
    SecretMaskingExtension,
    TranscriberExtension,
)

__all__ = [
    "LoggingExtension",
    "PermissionEnforcementExtension",
    "SecretMaskingExtension",
    "TranscriberExtension",
]
