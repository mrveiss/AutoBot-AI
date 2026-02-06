# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Permission Matcher - Claude Code Style Permission System

Provides glob-pattern matching for commands with precedence handling.
Supports Allow/Ask/Deny rules with wildcard patterns.

Precedence: DENY > ASK > ALLOW > DEFAULT (risk-based)

Usage:
    from backend.services.permission_matcher import PermissionMatcher, MatchResult

    matcher = PermissionMatcher()
    result, rule = matcher.match("Bash", "ls -la")

    if result == MatchResult.ALLOW:
        # Auto-approve the command
        pass
    elif result == MatchResult.ASK:
        # Request user approval
        pass
    elif result == MatchResult.DENY:
        # Block the command
        pass
    elif result == MatchResult.DEFAULT:
        # Fall back to risk-based assessment
        pass
"""

import fnmatch
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from autobot_shared.ssot_config import PermissionAction, PermissionMode, config

logger = logging.getLogger(__name__)


class MatchResult(Enum):
    """Result of permission rule matching."""

    ALLOW = "allow"  # Auto-approve without prompting
    ASK = "ask"  # Always prompt for approval
    DENY = "deny"  # Block completely
    DEFAULT = "default"  # Fall back to risk-based assessment


@dataclass
class PermissionRule:
    """A single permission rule."""

    tool: str
    pattern: str
    action: PermissionAction
    description: str = ""

    def matches(self, tool: str, command: str) -> bool:
        """
        Check if this rule matches the given tool and command.

        Uses fnmatch for glob-style pattern matching.
        Patterns support:
        - "*" matches any characters
        - "?" matches single character

        Args:
            tool: Tool name (e.g., "Bash", "Read", "Write")
            command: Full command string

        Returns:
            True if rule matches
        """
        # Tool must match exactly (case-insensitive)
        if self.tool.lower() != tool.lower():
            return False

        # Pattern matching using fnmatch (glob-style)
        return fnmatch.fnmatch(command, self.pattern)


class PermissionMatcher:
    """
    Glob-pattern matching for commands with precedence handling.

    Claude Code-style permission system that matches commands against
    allow/ask/deny rules with proper precedence.

    Precedence order: DENY > ASK > ALLOW > DEFAULT

    Attributes:
        allow_rules: List of rules that auto-approve commands
        ask_rules: List of rules that require user approval
        deny_rules: List of rules that block commands
        mode: Current permission mode (affects behavior)
        is_admin: Whether current user has admin privileges
    """

    def __init__(
        self,
        rules_file: Optional[str] = None,
        mode: Optional[PermissionMode] = None,
        is_admin: bool = False,
    ):
        """
        Initialize permission matcher with rules.

        Args:
            rules_file: Path to permission rules YAML file.
                       If not provided, uses config.permission.rules_file
            mode: Permission mode to use. If not provided, uses config.permission.mode
            is_admin: Whether current user has admin privileges
        """
        self.allow_rules: List[PermissionRule] = []
        self.ask_rules: List[PermissionRule] = []
        self.deny_rules: List[PermissionRule] = []

        # Set mode from config or parameter
        self.mode = mode or config.permission.mode
        self.is_admin = is_admin

        # Load rules from file
        rules_path = rules_file or config.permission.rules_file
        self._load_rules(rules_path)

        logger.info(
            f"PermissionMatcher initialized: mode={self.mode.value}, "
            f"is_admin={is_admin}, rules loaded: "
            f"allow={len(self.allow_rules)}, ask={len(self.ask_rules)}, "
            f"deny={len(self.deny_rules)}"
        )

    def _load_rules(self, rules_file: str) -> None:
        """
        Load permission rules from YAML file.

        Args:
            rules_file: Path to the YAML rules file
        """
        try:
            rules_path = Path(rules_file)
            if not rules_path.is_absolute():
                # Relative to project root
                rules_path = Path(__file__).parent.parent.parent / rules_file

            if not rules_path.exists():
                logger.warning(f"Permission rules file not found: {rules_path}")
                return

            with open(rules_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data:
                logger.warning("Empty permission rules file")
                return

            default_rules = data.get("default_rules", {})

            # Load allow rules
            for rule_data in default_rules.get("allow", []):
                self.allow_rules.append(
                    PermissionRule(
                        tool=rule_data.get("tool", "Bash"),
                        pattern=rule_data.get("pattern", ""),
                        action=PermissionAction.ALLOW,
                        description=rule_data.get("description", ""),
                    )
                )

            # Load ask rules
            for rule_data in default_rules.get("ask", []):
                self.ask_rules.append(
                    PermissionRule(
                        tool=rule_data.get("tool", "Bash"),
                        pattern=rule_data.get("pattern", ""),
                        action=PermissionAction.ASK,
                        description=rule_data.get("description", ""),
                    )
                )

            # Load deny rules
            for rule_data in default_rules.get("deny", []):
                self.deny_rules.append(
                    PermissionRule(
                        tool=rule_data.get("tool", "Bash"),
                        pattern=rule_data.get("pattern", ""),
                        action=PermissionAction.DENY,
                        description=rule_data.get("description", ""),
                    )
                )

            logger.debug(
                f"Loaded {len(self.allow_rules)} allow, "
                f"{len(self.ask_rules)} ask, {len(self.deny_rules)} deny rules"
            )

        except Exception as e:
            logger.error(f"Failed to load permission rules: {e}")

    def match(
        self, tool: str, command: str
    ) -> Tuple[MatchResult, Optional[PermissionRule]]:
        """
        Match a command against permission rules.

        Applies precedence: DENY > ASK > ALLOW > DEFAULT

        Args:
            tool: Tool name (e.g., "Bash", "Read", "Write")
            command: Full command string

        Returns:
            Tuple of (MatchResult, matched_rule or None)

        Example:
            result, rule = matcher.match("Bash", "ls -la")
            if result == MatchResult.ALLOW:
                logger.info(f"Auto-approved by rule: {rule.description}")
        """
        # Check mode overrides first
        mode_result = self._check_mode_override(tool, command)
        if mode_result is not None:
            return mode_result, None

        # Precedence: DENY > ASK > ALLOW > DEFAULT

        # 1. Check DENY rules first (highest precedence)
        for rule in self.deny_rules:
            if rule.matches(tool, command):
                logger.debug(f"DENY rule matched: {rule.pattern}")
                return MatchResult.DENY, rule

        # 2. Check ASK rules (second highest)
        for rule in self.ask_rules:
            if rule.matches(tool, command):
                logger.debug(f"ASK rule matched: {rule.pattern}")
                return MatchResult.ASK, rule

        # 3. Check ALLOW rules (third)
        for rule in self.allow_rules:
            if rule.matches(tool, command):
                logger.debug(f"ALLOW rule matched: {rule.pattern}")
                return MatchResult.ALLOW, rule

        # 4. No rule matched - use DEFAULT (risk-based)
        logger.debug(f"No rule matched for {tool}: {command[:50]}...")
        return MatchResult.DEFAULT, None

    def _check_mode_override(
        self, tool: str, command: str
    ) -> Optional[MatchResult]:
        """
        Check if permission mode overrides normal rule matching.

        Args:
            tool: Tool name
            command: Command string

        Returns:
            MatchResult if mode override applies, None otherwise
        """
        # Admin-only modes require admin privileges
        if config.permission.is_admin_only_mode(self.mode) and not self.is_admin:
            logger.warning(
                f"Non-admin user attempted to use admin-only mode: {self.mode.value}"
            )
            # Fall through to normal rule matching
            return None

        # Mode-specific behavior
        if self.mode == PermissionMode.BYPASS:
            # bypassPermissions: Skip all permission checks (ADMIN ONLY)
            if self.is_admin:
                logger.debug("BYPASS mode: Auto-allowing all commands (admin)")
                return MatchResult.ALLOW
            # Non-admin can't use bypass mode
            return None

        if self.mode == PermissionMode.DONT_ASK:
            # dontAsk: Auto-approve everything except DENY rules (ADMIN ONLY)
            if self.is_admin:
                # Still check deny rules
                for rule in self.deny_rules:
                    if rule.matches(tool, command):
                        logger.debug(f"DONT_ASK mode: DENY rule still applies: {rule.pattern}")
                        return MatchResult.DENY
                logger.debug("DONT_ASK mode: Auto-allowing (admin, no deny rule)")
                return MatchResult.ALLOW
            return None

        if self.mode == PermissionMode.PLAN:
            # plan: All write operations require approval
            # This is a hint to the system, not enforced here
            # Write tools should check this mode and require approval
            return None

        if self.mode == PermissionMode.ACCEPT_EDITS:
            # acceptEdits: Accept file edits without approval
            # This affects Write/Edit tools, handled by those tools
            return None

        # DEFAULT mode - use normal rule matching
        return None

    def add_rule(
        self,
        tool: str,
        pattern: str,
        action: PermissionAction,
        description: str = "",
    ) -> bool:
        """
        Add a new permission rule dynamically.

        Args:
            tool: Tool name to match
            pattern: Glob pattern to match command
            action: Permission action (allow/ask/deny)
            description: Human-readable description

        Returns:
            True if rule was added successfully

        Note:
            Adding ALLOW rules for dangerous patterns requires admin privileges.
        """
        # Security check: Only admins can add ALLOW rules
        if action == PermissionAction.ALLOW and not self.is_admin:
            logger.warning("Non-admin attempted to add ALLOW rule")
            return False

        rule = PermissionRule(
            tool=tool,
            pattern=pattern,
            action=action,
            description=description,
        )

        if action == PermissionAction.ALLOW:
            self.allow_rules.append(rule)
        elif action == PermissionAction.ASK:
            self.ask_rules.append(rule)
        elif action == PermissionAction.DENY:
            self.deny_rules.append(rule)

        logger.info(f"Added {action.value} rule: {tool}({pattern})")
        return True

    def remove_rule(self, tool: str, pattern: str) -> bool:
        """
        Remove a permission rule by tool and pattern.

        Args:
            tool: Tool name
            pattern: Glob pattern

        Returns:
            True if rule was found and removed
        """
        for rule_list in [self.allow_rules, self.ask_rules, self.deny_rules]:
            for rule in rule_list[:]:  # Iterate over copy
                if rule.tool.lower() == tool.lower() and rule.pattern == pattern:
                    rule_list.remove(rule)
                    logger.info(f"Removed {rule.action.value} rule: {tool}({pattern})")
                    return True

        return False

    def get_all_rules(self) -> Dict[str, List[Dict]]:
        """
        Get all rules organized by action.

        Returns:
            Dictionary with 'allow', 'ask', 'deny' keys containing rule lists
        """
        return {
            "allow": [
                {
                    "tool": r.tool,
                    "pattern": r.pattern,
                    "description": r.description,
                }
                for r in self.allow_rules
            ],
            "ask": [
                {
                    "tool": r.tool,
                    "pattern": r.pattern,
                    "description": r.description,
                }
                for r in self.ask_rules
            ],
            "deny": [
                {
                    "tool": r.tool,
                    "pattern": r.pattern,
                    "description": r.description,
                }
                for r in self.deny_rules
            ],
        }

    def set_mode(self, mode: PermissionMode) -> bool:
        """
        Set the permission mode.

        Args:
            mode: New permission mode

        Returns:
            True if mode was set, False if not permitted (non-admin + admin mode)
        """
        # Check if user can use this mode
        if config.permission.is_admin_only_mode(mode) and not self.is_admin:
            logger.warning(
                f"Non-admin user cannot set admin-only mode: {mode.value}"
            )
            return False

        self.mode = mode
        logger.info(f"Permission mode set to: {mode.value}")
        return True

    def get_mode(self) -> PermissionMode:
        """Get current permission mode."""
        return self.mode

    def get_allowed_modes(self) -> List[PermissionMode]:
        """Get list of modes allowed for current user role."""
        return config.permission.get_allowed_modes_for_role(self.is_admin)


# Singleton instance for easy access
_matcher_instance: Optional[PermissionMatcher] = None


def get_permission_matcher(
    is_admin: bool = False, reload: bool = False
) -> PermissionMatcher:
    """
    Get or create the global permission matcher instance.

    Args:
        is_admin: Whether current user has admin privileges
        reload: Force reload of rules from file

    Returns:
        PermissionMatcher instance
    """
    global _matcher_instance

    if _matcher_instance is None or reload:
        _matcher_instance = PermissionMatcher(is_admin=is_admin)

    # Update admin status if changed
    if _matcher_instance.is_admin != is_admin:
        _matcher_instance.is_admin = is_admin

    return _matcher_instance
