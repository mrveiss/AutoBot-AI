# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Command Approval Manager - Reusable Command Approval System

Provides reusable command approval logic that can be used across:
- Agent terminal sessions
- Direct user terminal sessions
- SSH connections
- File operations
- API calls
- Any system requiring command risk assessment and approval

Key Features:
- Static permission checking (no state required)
- Agent role-based permissions
- Auto-approve rules management
- Risk-based approval decisions
- Supervised mode for guided dangerous actions
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from src.secure_command_executor import CommandRisk

logger = logging.getLogger(__name__)


class AgentRole(Enum):
    """Agent roles with different privilege levels"""

    CHAT_AGENT = "chat_agent"  # Chat agents (lowest privilege)
    AUTOMATION_AGENT = "automation_agent"  # Workflow automation agents
    SYSTEM_AGENT = "system_agent"  # System monitoring agents
    ADMIN_AGENT = "admin_agent"  # Administrative agents (highest privilege)


@dataclass
class AgentPermissions:
    """Permission configuration for an agent role"""

    max_risk: CommandRisk
    auto_approve_safe: bool = True
    auto_approve_moderate: bool = False
    allow_high: bool = False
    allow_dangerous: bool = False
    supervised_mode: bool = False  # Allows FORBIDDEN with approval

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format"""
        return {
            "max_risk": self.max_risk,
            "auto_approve_safe": self.auto_approve_safe,
            "auto_approve_moderate": self.auto_approve_moderate,
            "allow_high": self.allow_high,
            "allow_dangerous": self.allow_dangerous,
            "supervised_mode": self.supervised_mode,
        }


@dataclass
class AutoApproveRule:
    """Auto-approve rule for command patterns"""

    pattern: str
    risk_level: str
    created_at: float
    original_command: str


class CommandApprovalManager:
    """
    Reusable command approval and risk assessment system.

    This class provides both stateless (static) methods for permission checking
    and stateful methods for auto-approve rule management.

    Usage:
        # Stateless permission checking (no instance needed)
        allowed, reason = CommandApprovalManager.check_permission(
            agent_role=AgentRole.CHAT_AGENT,
            command_risk=CommandRisk.HIGH
        )

        # Needs approval decision (no instance needed)
        needs_approval = CommandApprovalManager.needs_approval(
            agent_role=AgentRole.CHAT_AGENT,
            command_risk=CommandRisk.MODERATE
        )

        # Auto-approve rules (requires instance for state management)
        manager = CommandApprovalManager()
        is_approved = await manager.check_auto_approve_rules(
            user_id="user123",
            command="ls -la",
            risk_level="safe"
        )
    """

    # Default permission configuration for each agent role
    DEFAULT_PERMISSIONS: Dict[AgentRole, AgentPermissions] = {
        AgentRole.CHAT_AGENT: AgentPermissions(
            max_risk=CommandRisk.MODERATE,
            auto_approve_safe=True,
            auto_approve_moderate=False,
            allow_high=False,
            allow_dangerous=False,
            supervised_mode=True,  # Allows FORBIDDEN with approval
        ),
        AgentRole.AUTOMATION_AGENT: AgentPermissions(
            max_risk=CommandRisk.HIGH,
            auto_approve_safe=True,
            auto_approve_moderate=True,
            allow_high=True,
            allow_dangerous=False,
        ),
        AgentRole.SYSTEM_AGENT: AgentPermissions(
            max_risk=CommandRisk.HIGH,
            auto_approve_safe=True,
            auto_approve_moderate=True,
            allow_high=True,
            allow_dangerous=False,
        ),
        AgentRole.ADMIN_AGENT: AgentPermissions(
            max_risk=CommandRisk.CRITICAL,
            auto_approve_safe=True,
            auto_approve_moderate=True,
            allow_high=True,
            allow_dangerous=True,
        ),
    }

    def __init__(self, custom_permissions: Optional[Dict[AgentRole, AgentPermissions]] = None):
        """
        Initialize command approval manager.

        Args:
            custom_permissions: Optional custom permission configuration.
                               If not provided, uses DEFAULT_PERMISSIONS.
        """
        # Use custom permissions or fall back to defaults
        self.agent_permissions = custom_permissions or self.DEFAULT_PERMISSIONS.copy()

        # Auto-approve rules storage
        # Format: {user_id: [AutoApproveRule, ...]}
        self.auto_approve_rules: Dict[str, List[AutoApproveRule]] = {}

        logger.info("CommandApprovalManager initialized")

    @staticmethod
    def check_permission(
        agent_role: AgentRole,
        command_risk: CommandRisk,
        permissions: Optional[Dict[AgentRole, AgentPermissions]] = None,
    ) -> Tuple[bool, str]:
        """
        Check if agent has permission to execute command at given risk level.

        This is a static method that can be called without an instance,
        making it reusable across the entire codebase.

        Args:
            agent_role: Role of the agent
            command_risk: Risk level of the command
            permissions: Optional custom permissions dict (uses defaults if not provided)

        Returns:
            Tuple of (allowed: bool, reason: str)

        Example:
            allowed, reason = CommandApprovalManager.check_permission(
                agent_role=AgentRole.CHAT_AGENT,
                command_risk=CommandRisk.HIGH
            )
            if not allowed:
                print(f"Permission denied: {reason}")
        """
        # Use provided permissions or defaults
        perms_dict = permissions or CommandApprovalManager.DEFAULT_PERMISSIONS
        perms = perms_dict.get(agent_role)

        if not perms:
            return False, f"Unknown agent role: {agent_role}"

        # Check supervised mode - allows FORBIDDEN commands with approval
        supervised_mode = perms.supervised_mode

        # Map risk levels to numerical values for comparison
        risk_levels = {
            CommandRisk.SAFE: 0,
            CommandRisk.MODERATE: 1,
            CommandRisk.HIGH: 2,
            CommandRisk.CRITICAL: 3,
            CommandRisk.FORBIDDEN: 4,
        }

        # In supervised mode, allow up to FORBIDDEN but require approval
        effective_max_risk = CommandRisk.FORBIDDEN if supervised_mode else perms.max_risk

        if risk_levels.get(command_risk, 999) > risk_levels.get(effective_max_risk, 0):
            if supervised_mode:
                return (
                    False,
                    f"Command risk {command_risk.value} exceeds supervised mode limit",
                )
            else:
                return (
                    False,
                    f"Command risk {command_risk.value} exceeds agent max risk {perms.max_risk.value} "
                    f"(enable supervised mode for guided dangerous actions)",
                )

        # Check specific risk permissions (not needed in supervised mode)
        if not supervised_mode:
            if command_risk == CommandRisk.HIGH and not perms.allow_high:
                return False, "Agent not permitted to execute HIGH risk commands"

            if command_risk == CommandRisk.CRITICAL and not perms.allow_dangerous:
                return False, "Agent not permitted to execute DANGEROUS commands"

        return True, "Permission granted"

    @staticmethod
    def needs_approval(
        agent_role: AgentRole,
        command_risk: CommandRisk,
        permissions: Optional[Dict[AgentRole, AgentPermissions]] = None,
    ) -> bool:
        """
        Check if command needs user approval based on role and risk.

        This is a static method that can be called without an instance.

        In supervised mode: HIGH/CRITICAL/FORBIDDEN commands require approval
        In normal mode: Only commands up to max_risk are allowed, HIGH+ require approval

        Args:
            agent_role: Role of the agent
            command_risk: Risk level of the command
            permissions: Optional custom permissions dict (uses defaults if not provided)

        Returns:
            True if approval is required, False if auto-approved

        Example:
            if CommandApprovalManager.needs_approval(
                agent_role=AgentRole.CHAT_AGENT,
                command_risk=CommandRisk.MODERATE
            ):
                print("User approval required")
        """
        # Use provided permissions or defaults
        perms_dict = permissions or CommandApprovalManager.DEFAULT_PERMISSIONS
        perms = perms_dict.get(agent_role)

        if not perms:
            # Unknown role - require approval as safety measure
            return True

        supervised_mode = perms.supervised_mode

        # In supervised mode, HIGH/CRITICAL/FORBIDDEN always need approval
        if supervised_mode and command_risk in [
            CommandRisk.HIGH,
            CommandRisk.CRITICAL,
            CommandRisk.FORBIDDEN,
        ]:
            return True

        # SAFE commands can be auto-approved if permitted
        if command_risk == CommandRisk.SAFE:
            return not perms.auto_approve_safe

        # MODERATE commands need approval unless auto-approved
        if command_risk == CommandRisk.MODERATE:
            return not perms.auto_approve_moderate

        # HIGH/CRITICAL/FORBIDDEN always need approval
        return True

    async def check_auto_approve_rules(
        self,
        user_id: str,
        command: str,
        risk_level: str,
    ) -> bool:
        """
        Check if command matches any auto-approve rules for user.

        Args:
            user_id: User ID to check rules for
            command: Command to check
            risk_level: Risk level of the command

        Returns:
            True if command should be auto-approved

        Example:
            manager = CommandApprovalManager()
            if await manager.check_auto_approve_rules("user123", "ls -la", "safe"):
                print("Auto-approved by rule")
        """
        try:
            if user_id not in self.auto_approve_rules:
                return False

            pattern = self._extract_command_pattern(command)
            rules = self.auto_approve_rules[user_id]

            for rule in rules:
                # Match pattern and risk level
                if rule.pattern == pattern and rule.risk_level == risk_level:
                    logger.info(
                        f"Auto-approve rule matched for user {user_id}: "
                        f"pattern='{pattern}', risk={risk_level}"
                    )
                    return True

            return False

        except Exception as e:
            logger.error(f"Failed to check auto-approve rules: {e}")
            return False

    async def store_auto_approve_rule(
        self,
        user_id: str,
        command: str,
        risk_level: str,
    ) -> bool:
        """
        Store an auto-approve rule for future similar commands.

        Args:
            user_id: User who created the rule
            command: Command that was approved
            risk_level: Risk level of the command

        Returns:
            True if rule was stored successfully

        Example:
            manager = CommandApprovalManager()
            await manager.store_auto_approve_rule("user123", "ls -la", "safe")
        """
        try:
            # Extract command pattern (first word + arguments pattern)
            pattern = self._extract_command_pattern(command)

            # Create rule
            rule = AutoApproveRule(
                pattern=pattern,
                risk_level=risk_level,
                created_at=time.time(),
                original_command=command,
            )

            # Store in memory (could be persisted to Redis later)
            if user_id not in self.auto_approve_rules:
                self.auto_approve_rules[user_id] = []

            self.auto_approve_rules[user_id].append(rule)

            logger.info(
                f"Auto-approve rule stored for user {user_id}: "
                f"pattern='{pattern}', risk={risk_level}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to store auto-approve rule: {e}")
            return False

    @staticmethod
    def _extract_command_pattern(command: str) -> str:
        """
        Extract a pattern from a command for auto-approve matching.

        Examples:
            "ls -la /home" -> "ls *"
            "cat file.txt" -> "cat *"
            "git status" -> "git status"

        Args:
            command: Full command string

        Returns:
            Command pattern for matching
        """
        parts = command.split()
        if len(parts) == 0:
            return command

        # First word is the base command
        base_cmd = parts[0]

        # If there are arguments, use wildcard pattern
        if len(parts) > 1:
            # For commands with subcommands (like git status), preserve them
            if base_cmd in ["git", "docker", "kubectl", "npm", "yarn"]:
                if len(parts) >= 2:
                    return f"{base_cmd} {parts[1]} *"
            # For simple commands, use wildcard
            return f"{base_cmd} *"

        # No arguments - exact match
        return base_cmd

    def get_user_rules(self, user_id: str) -> List[AutoApproveRule]:
        """
        Get all auto-approve rules for a user.

        Args:
            user_id: User ID

        Returns:
            List of auto-approve rules
        """
        return self.auto_approve_rules.get(user_id, [])

    def clear_user_rules(self, user_id: str) -> bool:
        """
        Clear all auto-approve rules for a user.

        Args:
            user_id: User ID

        Returns:
            True if rules were cleared
        """
        if user_id in self.auto_approve_rules:
            del self.auto_approve_rules[user_id]
            logger.info(f"Cleared auto-approve rules for user {user_id}")
            return True
        return False
