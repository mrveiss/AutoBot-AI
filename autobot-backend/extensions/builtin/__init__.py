# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Built-in extensions for the extension hooks system.

Issue #658: Provides default extensions that demonstrate the
extension system and provide useful functionality.

Issue #3009: Adds PermissionEnforcementExtension for per-operation RBAC.
Issue #9044: Adds TranscriberExtension for the transcriber module.
"""

from extensions.builtin.logging_extension import LoggingExtension
from extensions.builtin.permission_enforcement import PermissionEnforcementExtension
from extensions.builtin.secret_masking import SecretMaskingExtension
from extensions.builtin.transcriber_extension import TranscriberExtension

__all__ = [
    "LoggingExtension",
    "PermissionEnforcementExtension",
    "SecretMaskingExtension",
    "TranscriberExtension",
]
