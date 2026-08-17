# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Built-in extensions for the extension hooks system.

Issue #658: Provides default extensions that demonstrate the
extension system and provide useful functionality.

Issue #3009: Adds PermissionEnforcementExtension for per-operation RBAC.
Issue #9044: Adds TranscriberExtension for the transcriber module.
Issue #14280: Adds TelemetryPromptMiddleware, relocated from a plugin.json
that could never load (it shipped an Extension subclass, not a BasePlugin).
"""

from middleware.builtin.logging_extension import LoggingExtension
from middleware.builtin.permission_enforcement import PermissionEnforcementExtension
from middleware.builtin.secret_masking import SecretMaskingExtension
from middleware.builtin.telemetry_prompt_middleware import TelemetryPromptMiddleware
from middleware.builtin.transcriber_extension import TranscriberExtension

__all__ = [
    "LoggingExtension",
    "PermissionEnforcementExtension",
    "SecretMaskingExtension",
    "TelemetryPromptMiddleware",
    "TranscriberExtension",
]
