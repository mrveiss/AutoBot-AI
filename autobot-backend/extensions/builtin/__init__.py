# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Built-in extensions for the extension hooks system.

Issue #658: Provides default extensions that demonstrate the
extension system and provide useful functionality.
"""

from extensions.builtin.logging_extension import LoggingExtension
from extensions.builtin.secret_masking import SecretMaskingExtension

__all__ = [
    "LoggingExtension",
    "SecretMaskingExtension",
]
