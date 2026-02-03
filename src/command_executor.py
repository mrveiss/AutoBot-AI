# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
DEPRECATED: This module redirects to secure_command_executor.py

All command execution functionality has been migrated to SecureCommandExecutor
with enhanced security controls, validation, and auditing.

This file exists only for backward compatibility.

Migration Status: Security Enhancement (2025-11-18)
Expected Removal: After verification period (2025-12-01)
Production Usage: None (zero imports found)

Usage:
    # Old import (deprecated but still works):
    from src.command_executor import CommandExecutor

    # New recommended import:
    from src.secure_command_executor import SecureCommandExecutor

Security Notes:
- SecureCommandExecutor provides comprehensive security validation
- Commands are risk-assessed and may be blocked for safety
- Docker sandboxing available for high-risk commands
- Full audit logging of all command execution
"""

import warnings

# Emit deprecation warning
warnings.warn(
    "src.command_executor is deprecated. "
    "Use src.secure_command_executor.SecureCommandExecutor instead. "
    "This compatibility shim will be removed in future version.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export SecureCommandExecutor as CommandExecutor for backward compatibility
from src.secure_command_executor import (
    CommandRisk,
)
from src.secure_command_executor import SecureCommandExecutor as CommandExecutor
from src.secure_command_executor import (
    SecurityPolicy,
)

__all__ = [
    "CommandExecutor",
    "SecurityPolicy",
    "CommandRisk",
]
