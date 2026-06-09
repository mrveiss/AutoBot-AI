# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Built-in extensions for the extension hooks system.

Issue #658: Provides default extensions that demonstrate the
extension system and provide useful functionality.

Issue #3009: Adds PermissionEnforcementExtension for per-operation RBAC.
"""

from middleware.builtin.logging_extension import LoggingExtension
from middleware.builtin.permission_enforcement import PermissionEnforcementExtension
from middleware.builtin.secret_masking import SecretMaskingExtension

__all__ = [
    "LoggingExtension",
    "PermissionEnforcementExtension",
    "SecretMaskingExtension",
]
