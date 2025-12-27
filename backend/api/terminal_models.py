# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Terminal API Models - Pydantic models and enums for terminal operations.

This module contains all Pydantic models used by the terminal API endpoints.
Extracted from terminal.py for better maintainability (Issue #185).

Models:
- SecurityLevel: Security levels for terminal access
- CommandRiskLevel: Risk assessment levels for commands
- CommandRequest: Request model for command execution
- TerminalSessionRequest: Request model for session creation
- TerminalInputRequest: Request model for terminal input
- WorkflowControlRequest: Request model for workflow control
- ToolInstallRequest: Request model for tool installation

Constants:
- RISKY_COMMAND_PATTERNS: Patterns for high-risk commands
- MODERATE_RISK_PATTERNS: Patterns for moderate-risk commands

Related Issues: #185 (Split oversized files)
"""

from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel


class SecurityLevel(Enum):
    """Security levels for terminal access"""

    STANDARD = "standard"
    ELEVATED = "elevated"
    RESTRICTED = "restricted"


class CommandRiskLevel(Enum):
    """Risk assessment levels for commands"""

    SAFE = "safe"
    MODERATE = "moderate"
    HIGH = "high"
    DANGEROUS = "dangerous"


# Request/Response Models
class CommandRequest(BaseModel):
    command: str
    description: Optional[str] = None
    require_confirmation: Optional[bool] = True
    timeout: Optional[float] = 30.0
    working_directory: Optional[str] = None
    environment: Optional[Dict[str, str]] = None


class TerminalSessionRequest(BaseModel):
    user_id: Optional[str] = "default"
    conversation_id: Optional[str] = None  # Link to chat session for logging
    chat_id: Optional[str] = None  # For chat-scoped SSH keys (Issue #211)
    security_level: Optional[SecurityLevel] = SecurityLevel.STANDARD
    enable_logging: Optional[bool] = True
    enable_workflow_control: Optional[bool] = True
    initial_directory: Optional[str] = None
    setup_ssh_keys: Optional[bool] = False  # Auto-setup SSH keys (Issue #211)
    ssh_key_names: Optional[list] = None  # Specific SSH keys to load (Issue #211)


class TerminalInputRequest(BaseModel):
    text: str
    is_password: Optional[bool] = False


class WorkflowControlRequest(BaseModel):
    action: str  # pause, resume, approve_step, cancel
    workflow_id: Optional[str] = None
    step_id: Optional[str] = None
    data: Optional[Dict] = None


class ToolInstallRequest(BaseModel):
    tool_name: str
    package_name: Optional[str] = None
    install_method: Optional[str] = "auto"
    custom_command: Optional[str] = None
    update_first: Optional[bool] = True


class SSHKeySetupRequest(BaseModel):
    """Request model for SSH key setup in terminal sessions (Issue #211)."""

    chat_id: Optional[str] = None  # For chat-scoped keys
    include_general: Optional[bool] = True  # Include general-scoped keys
    key_names: Optional[list] = None  # Specific keys to load


class SSHKeyAgentRequest(BaseModel):
    """Request model for adding SSH key to ssh-agent (Issue #211)."""

    key_name: str
    passphrase: Optional[str] = None  # For encrypted keys


# Security patterns for command risk assessment
RISKY_COMMAND_PATTERNS = [
    # File system destructive operations
    "rm -r",
    "rm -r",
    "sudo rm",
    "rmdir",
    # Disk operations
    "dd if=",
    "mkfs",
    "fdisk",
    "parted",
    # Permission changes
    "chmod 777",
    "chmod -R 777",
    "chown -R",
    # System-level operations
    "> /dev/",
    "/dev/sda",
    "/dev/sdb",
    # Network security
    "iptables -F",
    "ufw disable",
    # System shutdown
    "shutdown",
    "reboot",
    "halt",
    "powerof",
    # Package management (can be risky)
    "apt-get remove",
    "yum remove",
    "rm /etc/",
    # Process killing
    "kill -9",
    "killall -9",
]

MODERATE_RISK_PATTERNS = [
    "sudo",
    "su -",
    "chmod",
    "chown",
    "apt-get install",
    "yum install",
    "pip install",
    "systemctl",
    "service",
    "mount",
    "umount",
]
