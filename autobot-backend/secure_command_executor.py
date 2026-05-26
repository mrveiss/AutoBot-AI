# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Secure Command Executor with Sandboxing and Permission Controls
Implements security measures to prevent arbitrary command execution
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shlex
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Tuple

from autobot_shared.async_compat import run_or_schedule
from autobot_shared.logging_manager import get_logger
from constants.network_constants import NetworkConstants
from security.command_patterns import (
    FORBIDDEN_COMMANDS,
    HIGH_RISK_COMMANDS,
    MODERATE_RISK_COMMANDS,
    SAFE_COMMANDS,
    SENSITIVE_REDIRECT_PATHS,
    SYSTEM_PATHS,
    check_dangerous_patterns,
)
from services.tool_output_filter import get_tool_output_filter
from utils.command_utils import execute_shell_command

# Permission system imports (lazy to avoid circular imports)
if TYPE_CHECKING:
    from services.approval_memory import ApprovalMemoryManager
    from services.permission_matcher import PermissionMatcher

logger = get_logger(__name__)


# #7375: env-var prefix injection — surfaced by #7367 test rot triage.
# Production previously classified `PATH=/x:$PATH ls` and
# `LD_PRELOAD=/x.so ls` as MODERATE because the base-command lookup hit
# `ls` (a SAFE/MODERATE command) without parsing the env-var prefix as a
# distinct injection vector. Both are real attacker techniques:
#   - PATH manipulation shadows standard binaries (sudo helpers, cron,
#     login shells) by prepending an attacker-controlled directory.
#   - LD_PRELOAD / LD_LIBRARY_PATH / DYLD_INSERT_LIBRARIES hijack any
#     dynamic-linker symbol before the target binary runs — used in
#     container-escape and privilege-escalation chains.
#   - IFS / BASH_ENV / ENV affect shell parsing in subshells.
#   - PYTHONPATH / PERL5LIB / RUBYLIB / NODE_PATH inject malicious
#     libraries into interpreter startup.
_ENV_VAR_PREFIX_RE = re.compile(r"^\s*(?:[A-Za-z_][A-Za-z0-9_]*=(?:'[^']*'|\"[^\"]*\"|\S*)\s+)+")
_DANGEROUS_ENV_VARS = frozenset(
    {
        # Linker / loader hijack
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "LD_AUDIT",
        "DYLD_INSERT_LIBRARIES",
        "DYLD_LIBRARY_PATH",
        # Path / executable resolution
        "PATH",
        # Shell parsing / startup
        "IFS",
        "BASH_ENV",
        "ENV",
        "PROMPT_COMMAND",
        # #7406: SHELL controls which interpreter `sudo -E` (and other env-
        # preserving wrappers) invoke — `SHELL=/bin/sh; sudo -E sh` is a
        # real escalation chain.
        "SHELL",
        # Interpreter library paths
        "PYTHONPATH",
        "PERL5LIB",
        "RUBYLIB",
        "NODE_PATH",
        "GEM_PATH",
        # Process tracing
        "LD_DEBUG",
    }
)


# #7384: argument-aware risk for tools whose base command is allowlisted
# but whose flags / arguments elevate them to attack vectors.
# Same family as #7375 (env-var prefix) — the base command (`docker`,
# `find`, `dig`) lookup says SAFE/MODERATE, but specific argument shapes
# turn them into container-escape, SUID-recon, or DNS-tunneling vectors.
_DOCKER_ESCAPE_FLAGS = (
    "--privileged",
    "--net=host",
    "--network=host",
    "--pid=host",
    "--ipc=host",
    "--uts=host",
    "--userns=host",
    "--cap-add",
    "-v /:",
    "--volume=/:",
    "--device=",
    "--security-opt=seccomp=unconfined",
    "--security-opt=apparmor=unconfined",
)
# `find` argument shapes that signal SUID / setgid recon — used to locate
# privilege-escalation primitives. The wrapped `find` itself is benign
# (allowlisted MODERATE); these argument shapes elevate to HIGH.
_FIND_SUID_RECON_PATTERNS = (
    "-perm -4000",  # setuid bit (-4000)
    "-perm -2000",  # setgid bit (-2000)
    "-perm -u+s",  # setuid (symbolic)
    "-perm -g+s",  # setgid (symbolic)
    "-perm /4000",
    "-perm /2000",
)
# DNS-recon / DNS-tunneling vectors. Real attacker techniques for
# infiltration channels and external host enumeration. Worth at least
# MODERATE so they're audit-logged.
_DNS_RECON_COMMANDS = frozenset({"dig", "nslookup", "host", "whois", "drill"})

# #7406: ordering for CommandRisk so chained-command detection can pick the
# strictest risk across sub-commands. Strings are used here because the enum
# class is defined later in this module; the caller compares via this lookup.
_RISK_ORDER: Dict[str, int] = {
    "safe": 0,
    "moderate": 1,
    "high": 2,
    "critical": 3,
    "forbidden": 4,
}


def _check_argument_aware_risk(command: str) -> Tuple["CommandRisk", List[str]] | None:
    """#7384: detect attack vectors that base-command lookup misses.

    Returns ``(risk, reasons)`` for argument-shape-elevated commands,
    or ``None`` if no argument-aware rule fires. The caller short-circuits
    risk assessment so the more-specific reason wins over the generic
    base-command classification.
    """
    # Tokenise once; we use string membership for flag checks but a
    # token list for first-token (DNS) detection.
    try:
        tokens = shlex.split(command)
    except ValueError:
        # Malformed quoting; let the standard path handle it.
        return None
    if not tokens:
        return None

    # 1. Docker escape flags — `docker run --privileged …` etc.
    if tokens[0] == "docker":
        flagged_docker: List[str] = []
        # Cheap substring check for compound flags (`-v /:`, `--cap-add SYS_ADMIN`).
        for flag in _DOCKER_ESCAPE_FLAGS:
            if flag in command:
                flagged_docker.append(flag)
        # `--cap-add` may appear with `=` or as a separate arg — if any
        # token equals it AND a sibling token is supplied, count as flag.
        if "--cap-add" in tokens or any(t.startswith("--cap-add=") for t in tokens):
            if "--cap-add" not in flagged_docker:
                flagged_docker.append("--cap-add")
        if flagged_docker:
            return (
                CommandRisk.FORBIDDEN,
                [f"Docker escape flag: {flag}" for flag in flagged_docker],
            )

    # 2. `find` SUID / setgid recon.
    if tokens[0] == "find":
        for pattern in _FIND_SUID_RECON_PATTERNS:
            if pattern in command:
                return (CommandRisk.HIGH, [f"SUID/setgid recon: {pattern}"])

    # 3. DNS recon — first token (no env-var prefix has reached here, so
    # tokens[0] is the actual base command).
    if tokens[0] in _DNS_RECON_COMMANDS:
        return (
            CommandRisk.MODERATE,
            [f"DNS-recon command: {tokens[0]} (audit-logged)"],
        )

    # 4. #7406: `export VAR=value` shell-builtin form. Sibling of the
    # prefix-form #7375 check — same dangerous-var list, different syntax.
    # `export PATH=/x; ls` persists the var in the current shell so every
    # subsequent command runs with the attacker-controlled PATH.
    if tokens[0] == "export":
        for token in tokens[1:]:
            if "=" not in token:
                continue
            # Strip trailing shell separators (`;`, `&`, `&&`, etc.) that
            # shlex.split keeps glued to the value (e.g. `SHELL=/bin/sh;`).
            value_part = token.split("=", 1)[1].rstrip(";&|")
            var = token.split("=", 1)[0]
            if var in _DANGEROUS_ENV_VARS:
                return (
                    CommandRisk.FORBIDDEN,
                    [f"export of dangerous env-var: {var}={value_part!r}"],
                )

    # 5. #7406: `cmd1; cmd2` chained-command separator with a high-risk
    # right-hand side. shlex.split keeps `;` glued to the preceding token,
    # so split on it manually and recurse on each sub-command. Take the
    # highest risk seen across all sub-commands.
    if any(";" in t for t in tokens):
        # Re-split on the raw `;` separator to get the actual sub-command
        # boundaries (shlex preserves `;` as a literal — strip it back out).
        sub_commands = [s.strip() for s in command.split(";") if s.strip()]
        if len(sub_commands) > 1:
            from typing import cast

            highest_risk: "CommandRisk" | None = None
            all_reasons: List[str] = []
            for sub in sub_commands:
                sub_result = _check_argument_aware_risk(sub)
                if sub_result is None:
                    continue
                sub_risk, sub_reasons = sub_result
                # Take the strictest risk (FORBIDDEN > HIGH > MODERATE > SAFE).
                if highest_risk is None or _RISK_ORDER[sub_risk.value] > _RISK_ORDER[highest_risk.value]:
                    highest_risk = sub_risk
                all_reasons.extend(sub_reasons)
            if highest_risk is not None:
                return (
                    cast("CommandRisk", highest_risk),
                    [f"Chained command (`;` separator): {r}" for r in all_reasons],
                )

    return None


def _check_dangerous_env_var_prefix(command: str) -> List[str] | None:
    """#7375: detect env-var prefix injection BEFORE base-command lookup.

    Returns a list of dangerous env-var names found prefixed in the
    command, or ``None`` if none. The caller upgrades the risk to
    ``CommandRisk.FORBIDDEN`` since these prefixes shadow the linker /
    interpreter / shell startup independent of the command they wrap.
    """
    match = _ENV_VAR_PREFIX_RE.match(command)
    if not match:
        return None
    prefix = match.group(0)
    flagged: List[str] = []
    # Per-assignment: split by `=` to get the var name, ignore the value.
    # We use `shlex.split` because values may contain quoted strings with
    # whitespace (e.g. `PROMPT_COMMAND='rm -rf /'`) — naive `prefix.split()`
    # would tokenize on space and miss the var-name extraction.
    try:
        tokens = shlex.split(prefix)
    except ValueError:
        # Malformed quoting — fall back to whitespace split; if the prefix
        # is truly malformed it'll fail base-command validation downstream.
        tokens = prefix.split()
    for token in tokens:
        if "=" not in token:
            continue
        var_name = token.split("=", 1)[0]
        if var_name in _DANGEROUS_ENV_VARS:
            flagged.append(var_name)
    return flagged or None


# Issue #765: Path constants now imported from security.command_patterns


class CommandRisk(Enum):
    """Risk levels for commands"""

    SAFE = "safe"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"
    FORBIDDEN = "forbidden"


class SecurityPolicy:
    """Security policy for command execution.

    Issue #765: Now uses centralized patterns from security.command_patterns.
    """

    def __init__(self):
        """
        Initialize security policy with command classifications and path restrictions.

        Issue #281: Refactored from 148 lines to use extracted helper methods.
        Issue #765: Command sets now delegate to centralized command_patterns module.
        """
        # Issue #765: Use centralized command sets from security.command_patterns
        self.safe_commands = SAFE_COMMANDS
        self.moderate_commands = MODERATE_RISK_COMMANDS
        self.high_risk_commands = HIGH_RISK_COMMANDS
        self.forbidden_commands = FORBIDDEN_COMMANDS
        self.allowed_paths = self._get_allowed_paths()
        self.allowed_extensions = self._get_allowed_extensions()

    def _get_allowed_paths(self) -> list:
        """Allowed directories for file operations. Issue #281: Extracted helper."""
        return [
            Path.home(),  # User home directory
            Path("/tmp"),  # Temporary directory  # nosec B108
            Path("/var/tmp"),  # Var temporary  # nosec B108
            Path.cwd(),  # Current working directory
        ]

    def _get_allowed_extensions(self) -> set:
        """File extensions that can be modified. Issue #281: Extracted helper."""
        return {
            ".txt",
            ".log",
            ".json",
            ".yaml",
            ".yml",
            ".md",
            ".py",
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
            ".vue",
            ".html",
            ".css",
            ".scss",
            ".sass",
            ".sh",
            ".bash",
            ".zsh",
            ".con",
            ".cfg",
            ".ini",
            ".env",
            ".csv",
            ".tsv",
            ".xml",
        }


class SecureCommandExecutor:
    """
    Secure command executor with sandboxing and permission controls.

    Supports two permission models:
    1. Risk-based (default): Commands assessed by risk level (SAFE/MODERATE/HIGH/FORBIDDEN)
    2. Claude Code-style: Glob-pattern rules with ALLOW/ASK/DENY/DEFAULT actions

    When permission_v2 is enabled, the order is:
    1. Check permission rules (DENY > ASK > ALLOW)
    2. Check approval memory (per-project remembered approvals)
    3. Fall back to risk-based assessment (DEFAULT case)
    """

    def __init__(
        self,
        policy: SecurityPolicy | None = None,
        require_approval_callback=None,
        use_docker_sandbox: bool = False,
        is_admin: bool = False,
        project_path: str | None = None,
        user_id: str | None = None,
    ):
        """
        Initialize secure command executor

        Args:
            policy: Security policy to use (default: SecurityPolicy())
            require_approval_callback: Async callback function for user approval
            use_docker_sandbox: Whether to execute commands in Docker container
            is_admin: Whether current user has admin privileges (for permission v2)
            project_path: Current project path (for approval memory)
            user_id: Current user ID (for approval memory)
        """
        self.policy = policy or SecurityPolicy()
        self.require_approval_callback = require_approval_callback
        self.use_docker_sandbox = use_docker_sandbox
        self.docker_image = "autobot-sandbox:latest"

        # Permission v2 attributes
        self.is_admin = is_admin
        self.project_path = project_path
        self.user_id = user_id

        # Lazy-loaded permission matcher and approval memory
        self._permission_matcher: "PermissionMatcher" | None = None
        self._approval_memory: "ApprovalMemoryManager" | None = None

        # Command history for audit
        self.command_history: List[Dict[str, Any]] = []

    def _extract_command_name(self, command: str) -> str:
        """Extract the base command name from a command string"""
        try:
            parts = shlex.split(command)
            if parts:
                # Handle cases like /usr/bin/ls
                return os.path.basename(parts[0])
        except ValueError:
            # Fallback for malformed commands
            parts = command.split()
            if parts:
                return os.path.basename(parts[0])
        return ""

    def _check_dangerous_patterns(self, command: str) -> List[str]:
        """Check command for dangerous patterns.

        Issue #765: Delegates to centralized check_dangerous_patterns function.
        """
        matches = check_dangerous_patterns(command)
        # Return descriptions of matched patterns for backward compatibility
        return [match[0] for match in matches]

    def _get_permission_matcher(self) -> "PermissionMatcher" | None:
        """
        Get or create the permission matcher (lazy initialization).

        Returns:
            PermissionMatcher instance if permission v2 is enabled, None otherwise
        """
        from autobot_shared.ssot_config import config

        if not config.permission.enabled:
            return None

        if self._permission_matcher is None:
            try:
                from services.permission_matcher import PermissionMatcher

                self._permission_matcher = PermissionMatcher(is_admin=self.is_admin)
            except ImportError as e:
                logger.warning(f"Permission matcher not available: {e}")
                return None

        return self._permission_matcher

    def _get_approval_memory(self) -> "ApprovalMemoryManager" | None:
        """
        Get or create the approval memory manager (lazy initialization).

        Returns:
            ApprovalMemoryManager instance if enabled, None otherwise
        """
        from autobot_shared.ssot_config import config

        if not config.permission.enabled or not config.permission.approval_memory_enabled:
            return None

        if self._approval_memory is None:
            try:
                from services.approval_memory import ApprovalMemoryManager

                self._approval_memory = ApprovalMemoryManager()
            except ImportError as e:
                logger.warning(f"Approval memory not available: {e}")
                return None

        return self._approval_memory

    def _build_rule_info(
        self,
        action: str,
        rule: Any,
        default_description: str,
        from_memory: bool = False,
    ) -> Dict[str, Any]:
        """
        Build a rule_info dictionary for permission rule results.

        Issue #620.

        Args:
            action: The permission action (allow, ask, deny)
            rule: The matched permission rule object (may be None)
            default_description: Default description if rule has none
            from_memory: Whether approval came from memory

        Returns:
            Dictionary with action, pattern, description, and optionally from_memory
        """
        rule_info = {
            "action": action,
            "pattern": rule.pattern if rule else None,
            "description": rule.description if rule else default_description,
        }
        if from_memory:
            rule_info["from_memory"] = True
        return rule_info

    async def _process_permission_match(
        self, result: Any, rule: Any, command: str, tool: str
    ) -> Tuple[str | None, Dict[str, Any] | None]:
        """
        Process a permission match result and return action/rule_info.

        Issue #620.

        Args:
            result: MatchResult enum value
            rule: Matched permission rule
            command: The command being checked
            tool: Tool name for memory check

        Returns:
            Tuple of (action, rule_info)
        """
        from services.permission_matcher import MatchResult

        if result == MatchResult.DENY:
            return "deny", self._build_rule_info("deny", rule, "Denied by permission rule")

        if result == MatchResult.ASK:
            return "ask", self._build_rule_info("ask", rule, "Requires approval")

        if result == MatchResult.ALLOW:
            from_memory = await self._check_approval_memory(command, tool)
            return "allow", self._build_rule_info("allow", rule, "Allowed by rule", from_memory)

        # DEFAULT - fall through to risk-based assessment
        if await self._check_approval_memory(command, tool):
            return "allow", {"action": "allow", "from_memory": True}

        return None, None

    async def check_permission_rules(
        self, command: str, tool: str = "Bash"
    ) -> Tuple[str | None, Dict[str, Any] | None]:
        """
        Check command against Claude Code-style permission rules.

        Called BEFORE risk assessment when permission v2 is enabled.

        Args:
            command: The command to check
            tool: The tool name (default: "Bash")

        Returns:
            Tuple of (action, rule_info) where:
            - action is "allow", "ask", "deny", or None (for default/risk-based)
            - rule_info contains matched rule details or None
        """
        matcher = self._get_permission_matcher()
        if not matcher:
            return None, None

        try:
            result, rule = matcher.match(tool, command)
            return await self._process_permission_match(result, rule, command, tool)

        except Exception as e:
            logger.error(f"Permission rule check failed: {e}")
            return None, None

    async def _check_approval_memory(self, command: str, tool: str = "Bash") -> bool:
        """
        Check if command is remembered in approval memory.

        Args:
            command: The command to check
            tool: The tool name

        Returns:
            True if command should be auto-approved from memory
        """
        if not self.project_path or not self.user_id:
            return False

        memory = self._get_approval_memory()
        if not memory:
            return False

        try:
            # Get risk level for memory check
            risk, _ = self.assess_command_risk(command)
            return await memory.check_remembered(
                project_path=self.project_path,
                command=command,
                user_id=self.user_id,
                risk_level=risk.value,
                tool=tool,
            )
        except Exception as e:
            logger.error(f"Approval memory check failed: {e}")
            return False

    async def store_approval_memory(
        self,
        command: str,
        risk_level: str,
        tool: str = "Bash",
        comment: str | None = None,
    ) -> bool:
        """
        Store a command approval in memory for future auto-approval.

        Called when user approves a command with "Remember" checkbox.

        Args:
            command: The approved command
            risk_level: Risk level of the command
            tool: Tool name
            comment: Optional approval comment

        Returns:
            True if stored successfully
        """
        if not self.project_path or not self.user_id:
            logger.debug("Cannot store approval: no project_path or user_id")
            return False

        memory = self._get_approval_memory()
        if not memory:
            return False

        try:
            return await memory.remember_approval(
                project_path=self.project_path,
                command=command,
                user_id=self.user_id,
                risk_level=risk_level,
                tool=tool,
                comment=comment,
            )
        except Exception as e:
            logger.error(f"Failed to store approval memory: {e}")
            return False

    def _assess_safe_command_risk(self, command: str) -> tuple[CommandRisk, List[str]]:
        """
        Assess risk for commands in the safe category with edge case checks.

        Issue #620.

        Args:
            command: The full command string

        Returns:
            (risk_level, list_of_reasons)
        """
        # Even safe commands can be risky with certain arguments
        if "sudo" in command or command.startswith("sudo"):
            return CommandRisk.HIGH, ["Uses sudo elevation"]

        # Check for output redirection to sensitive files (Issue #765)
        if ">" in command or ">>" in command:
            if any(sensitive in command for sensitive in SENSITIVE_REDIRECT_PATHS):
                return CommandRisk.HIGH, ["Redirects to sensitive location"]

        return CommandRisk.SAFE, ["Safe command"]

    def _check_command_category(self, base_command: str, command: str) -> tuple[CommandRisk, List[str]] | None:
        """
        Check command against policy categories and return risk if matched.

        Issue #620.

        Args:
            base_command: The extracted base command name
            command: The full command string

        Returns:
            (risk_level, list_of_reasons) if matched, None otherwise
        """
        if base_command in self.policy.forbidden_commands:
            return CommandRisk.FORBIDDEN, [f"Forbidden command: {base_command}"]

        if base_command in self.policy.high_risk_commands:
            return CommandRisk.HIGH, [f"High-risk command: {base_command}"]

        if base_command in self.policy.moderate_commands:
            reasons = [f"Moderate-risk command: {base_command}"]
            if any(path in command for path in SYSTEM_PATHS):
                reasons.append("Operates on system paths")
                return CommandRisk.HIGH, reasons
            return CommandRisk.MODERATE, reasons

        if base_command in self.policy.safe_commands:
            return self._assess_safe_command_risk(command)

        return None

    def assess_command_risk(self, command: str) -> tuple[CommandRisk, List[str]]:
        """
        Assess the risk level of a command.

        Issue #765: Uses centralized patterns from security.command_patterns.
        Issue #620: Refactored using extracted helper methods.

        Returns:
            (risk_level, list_of_reasons)
        """
        # #7375: env-var prefix injection check runs FIRST. `PATH=/x ls`
        # would otherwise resolve to base_command `ls` (SAFE/MODERATE) and
        # miss the linker/path hijack entirely. Also catches malformed
        # commands like `PROMPT_COMMAND='rm -rf /' bash` where
        # _extract_command_name returns empty — we want the more specific
        # FORBIDDEN reason ("Dangerous env-var prefix: PROMPT_COMMAND")
        # rather than the generic "Empty or malformed command".
        dangerous_env_vars = _check_dangerous_env_var_prefix(command)
        if dangerous_env_vars:
            reasons = [f"Dangerous env-var prefix: {var}" for var in dangerous_env_vars]
            return CommandRisk.FORBIDDEN, reasons

        # #7384: argument-aware risk for tools whose base command is
        # allowlisted but whose flags / arguments elevate them to attack
        # vectors — `docker run --privileged`, `find -perm -4000`, `dig`.
        # Same family as the env-var check above; runs before base-command
        # lookup so the more-specific reason wins.
        arg_aware = _check_argument_aware_risk(command)
        if arg_aware is not None:
            return arg_aware

        base_command = self._extract_command_name(command)

        if not base_command:
            return CommandRisk.FORBIDDEN, ["Empty or malformed command"]

        # Check dangerous patterns first (Issue #765: uses centralized function)
        dangerous_patterns = self._check_dangerous_patterns(command)
        if dangerous_patterns:
            reasons = [f"Dangerous pattern: {p}" for p in dangerous_patterns]
            return CommandRisk.FORBIDDEN, reasons

        # Check command categories
        category_result = self._check_command_category(base_command, command)
        if category_result:
            return category_result

        # Unknown command - treat as moderate risk
        return CommandRisk.MODERATE, [f"Unknown command: {base_command}"]

    async def _request_approval(self, command: str, risk: CommandRisk, reasons: List[str]) -> bool:
        """Request user approval for command execution"""
        if self.require_approval_callback:
            approval_data = {
                "command": command,
                "risk": risk.value,
                "reasons": reasons,
                "timestamp": asyncio.get_running_loop().time(),
            }
            return await self.require_approval_callback(approval_data)

        # If no callback, log and deny by default for safety
        logger.warning("No approval callback set. Denying command: %s", command)
        return False

    def _build_docker_command(self, command: str) -> str:
        """Build Docker command for sandboxed execution"""
        # Create a minimal sandbox container
        docker_cmd = [
            "docker",
            "run",
            "--rm",  # Remove container after execution
            "--read-only",  # Read-only root filesystem
            "--network",
            "none",  # No network access
            "--memory",
            "512m",  # Memory limit
            "--cpus",
            "1.0",  # CPU limit
            "--user",
            NetworkConstants.DEFAULT_USER_GROUP,  # Non-root user
            "-v",
            f"{os.getcwd()}:/workspace:ro",  # Mount current dir read-only
            "-w",
            "/workspace",
            self.docker_image,
            "sh",
            "-c",
            command,
        ]
        return " ".join(docker_cmd)

    def _build_blocked_result(
        self,
        risk: CommandRisk,
        reasons: List[str],
        message: str,
    ) -> Dict[str, Any]:
        """
        Build result dict for blocked/denied commands.

        Issue #281: Extracted helper for blocked result building.

        Args:
            risk: Risk level of command
            reasons: List of risk reasons
            message: Error message for stderr

        Returns:
            Result dict with error status and security info
        """
        return {
            "stdout": "",
            "stderr": message,
            "return_code": 1,
            "status": "error",
            "security": {"risk": risk.value, "reasons": reasons, "blocked": True},
        }

    def _build_error_result(
        self,
        risk: CommandRisk,
        reasons: List[str],
        error_type: str,
        error_msg: str,
    ) -> Dict[str, Any]:
        """
        Build result dict for execution errors.

        Issue #281: Extracted helper for error result building.

        Args:
            risk: Risk level of command
            reasons: List of risk reasons
            error_type: Type of error (timeout, error)
            error_msg: Error message

        Returns:
            Result dict with error status
        """
        return_code = 124 if error_type == "timeout" else 1
        security_info = {"risk": risk.value, "reasons": reasons, error_type: True}
        if error_type == "error":
            security_info["error"] = error_msg

        return {
            "stdout": "",
            "stderr": error_msg,
            "return_code": return_code,
            "status": "error",
            "security": security_info,
        }

    def _build_permission_deny_result(self, command: str, rule_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Issue #665: Extracted from run_shell_command to reduce function length.

        Build result dict for permission rule denied commands.

        Args:
            command: The denied command
            rule_info: Permission rule info dict

        Returns:
            Result dict with error status and permission info
        """
        logger.warning(f"Command denied by permission rule: {command}")
        description = rule_info.get("description", "Denied")
        return {
            "stdout": "",
            "stderr": f"Command denied by permission rule: {description}",
            "return_code": 1,
            "status": "error",
            "security": {
                "risk": "forbidden",
                "reasons": [rule_info.get("description", "Denied by rule")],
                "blocked": True,
                "permission_rule": rule_info,
            },
        }

    def _build_auto_approved_log_entry(
        self,
        command: str,
        risk: CommandRisk,
        reasons: List[str],
        rule_info: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """
        Issue #665: Extracted from run_shell_command to reduce function length.

        Build log entry for auto-approved commands.

        Args:
            command: The command being executed
            risk: Risk level of command
            reasons: Risk assessment reasons
            rule_info: Optional permission rule info

        Returns:
            Log entry dict for command history
        """
        auto_approved_by = "permission_rule"
        if rule_info and rule_info.get("from_memory"):
            auto_approved_by = "approval_memory"

        return {
            "command": command,
            "risk": risk.value,
            "reasons": reasons,
            "timestamp": asyncio.get_running_loop().time(),
            "approved": True,
            "executed": False,
            "auto_approved_by": auto_approved_by,
        }

    def _build_standard_log_entry(self, command: str, risk: CommandRisk, reasons: List[str]) -> Dict[str, Any]:
        """
        Issue #665: Extracted from run_shell_command to reduce function length.

        Build standard log entry for risk-based assessment.

        Args:
            command: The command being executed
            risk: Risk level of command
            reasons: Risk assessment reasons

        Returns:
            Log entry dict for command history
        """
        return {
            "command": command,
            "risk": risk.value,
            "reasons": reasons,
            "timestamp": asyncio.get_running_loop().time(),
            "approved": False,
            "executed": False,
        }

    async def _handle_forbidden_command(
        self,
        command: str,
        risk: CommandRisk,
        reasons: List[str],
        log_entry: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Issue #665: Extracted from run_shell_command to reduce function length.

        Handle forbidden commands by logging and returning blocked result.

        Args:
            command: The forbidden command
            risk: Risk level (should be FORBIDDEN)
            reasons: List of risk reasons
            log_entry: Log entry dict to update

        Returns:
            Blocked result dict
        """
        logger.error("Forbidden command blocked: %s", command)
        log_entry["error"] = "Command forbidden by security policy"
        self.command_history.append(log_entry)
        return self._build_blocked_result(risk, reasons, f"Command forbidden: {'; '.join(reasons)}")

    async def _handle_approval_flow(
        self,
        command: str,
        risk: CommandRisk,
        reasons: List[str],
        log_entry: Dict[str, Any],
        force_approval: bool,
        permission_action: str | None,
    ) -> Dict[str, Any] | None:
        """
        Issue #665: Extracted from run_shell_command to reduce function length.

        Handle approval flow for commands that need user approval.

        Args:
            command: The command to approve
            risk: Risk level of command
            reasons: Risk assessment reasons
            log_entry: Log entry dict to update
            force_approval: Whether to force approval
            permission_action: Permission action from rule check

        Returns:
            Blocked result dict if denied, None if approved
        """
        needs_approval = (
            force_approval or permission_action == "ask" or risk in {CommandRisk.HIGH, CommandRisk.MODERATE}
        )

        if needs_approval:
            approved = await self._request_approval(command, risk, reasons)
            log_entry["approved"] = approved

            if not approved:
                logger.warning("Command denied by user: %s", command)
                log_entry["error"] = "User denied execution"
                self.command_history.append(log_entry)
                return self._build_blocked_result(risk, reasons, "Command execution denied by user")

        return None

    def _build_execution_security_info(
        self,
        risk: CommandRisk,
        reasons: List[str],
        log_entry: Dict[str, Any],
        rule_info: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """
        Build security info dictionary for successful command execution.

        Issue #620.

        Args:
            risk: Risk level of command
            reasons: Risk assessment reasons
            log_entry: Log entry dict
            rule_info: Optional permission rule info

        Returns:
            Security info dictionary
        """
        security_info = {
            "risk": risk.value,
            "reasons": reasons,
            "sandboxed": self.use_docker_sandbox and risk != CommandRisk.SAFE,
            "approved": log_entry.get("approved", False),
        }

        if rule_info:
            security_info["permission_rule"] = rule_info
            if rule_info.get("from_memory"):
                security_info["auto_approved_by"] = "approval_memory"
            else:
                security_info["auto_approved_by"] = "permission_rule"

        return security_info

    def _prepare_command_for_execution(self, command: str, risk: CommandRisk) -> str:
        """
        Prepare command for execution, optionally wrapping in Docker sandbox.

        Issue #620.

        Args:
            command: The shell command
            risk: Risk level of command

        Returns:
            The command to execute (possibly wrapped in Docker)
        """
        if self.use_docker_sandbox and risk != CommandRisk.SAFE:
            logger.info("Executing in Docker sandbox: %s", command)
            return self._build_docker_command(command)
        return command

    def _handle_execution_error(
        self,
        command: str,
        risk: CommandRisk,
        reasons: List[str],
        log_entry: Dict[str, Any],
        error: Exception,
    ) -> Dict[str, Any]:
        """
        Handle command execution errors and build error result.

        Issue #620.

        Args:
            command: The command that failed
            risk: Risk level of command
            reasons: Risk assessment reasons
            log_entry: Log entry dict to update
            error: The exception that occurred

        Returns:
            Error result dictionary
        """
        if isinstance(error, asyncio.TimeoutError):
            logger.error("Command timed out: %s", command)
            log_entry["error"] = "Command timed out"
            self.command_history.append(log_entry)
            return self._build_error_result(risk, reasons, "timeout", "Command execution timed out after 5 minutes")

        logger.error("Command execution error: %s", error)
        log_entry["error"] = str(error)
        self.command_history.append(log_entry)
        return self._build_error_result(risk, reasons, "error", f"Error executing command: {error}")

    async def _execute_command(
        self,
        command: str,
        risk: CommandRisk,
        reasons: List[str],
        log_entry: Dict[str, Any],
        rule_info: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """
        Execute a command after permission/risk checks.

        Issue #620: Refactored using extracted helper methods.

        Args:
            command: The shell command to execute
            risk: Assessed risk level
            reasons: Risk assessment reasons
            log_entry: Log entry dict to update
            rule_info: Optional permission rule info

        Returns:
            Execution result dictionary
        """
        _filter = get_tool_output_filter()
        prepared_command = _filter.prepare_command(command)
        actual_command = self._prepare_command_for_execution(prepared_command, risk)

        try:
            result = await execute_shell_command(actual_command)
            log_entry["executed"] = True
            log_entry["return_code"] = result["return_code"]
            result["stdout"] = _filter.filter(
                prepared_command,
                result.get("stdout", ""),
                exit_code=result["return_code"],
            )
            self.command_history.append(log_entry)
            result["security"] = self._build_execution_security_info(risk, reasons, log_entry, rule_info)
            return result
        except Exception as e:
            return self._handle_execution_error(command, risk, reasons, log_entry, e)

    async def run_shell_command(self, command: str, force_approval: bool = False, tool: str = "Bash") -> Dict[str, Any]:
        """
        Securely execute a shell command with risk assessment and sandboxing.

        Issue #665: Refactored to under 50 lines using extracted helper methods.
        Permission v2 order: DENY > ASK > ALLOW rules, then risk-based assessment.

        Args:
            command: The shell command to execute
            force_approval: Force user approval regardless of risk level
            tool: Tool name for permission matching (default: "Bash")

        Returns:
            Dictionary containing execution results and security info
        """
        permission_action, rule_info = await self.check_permission_rules(command, tool)

        if permission_action == "deny":
            return self._build_permission_deny_result(command, rule_info)

        if permission_action == "allow":
            logger.info(f"Command auto-approved by permission rule: {command[:50]}...")
            risk, reasons = self.assess_command_risk(command)
            log_entry = self._build_auto_approved_log_entry(command, risk, reasons, rule_info)
            return await self._execute_command(command, risk, reasons, log_entry, rule_info)

        # Risk-based assessment fallback
        risk, reasons = self.assess_command_risk(command)
        log_entry = self._build_standard_log_entry(command, risk, reasons)

        if risk == CommandRisk.FORBIDDEN:
            return await self._handle_forbidden_command(command, risk, reasons, log_entry)

        denial_result = await self._handle_approval_flow(
            command, risk, reasons, log_entry, force_approval, permission_action
        )
        if denial_result:
            return denial_result

        return await self._execute_command(command, risk, reasons, log_entry)

    def get_command_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent command history for audit purposes"""
        return self.command_history[-limit:]

    def clear_history(self):
        """Clear command history"""
        self.command_history.clear()


# Example usage and testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    async def example_approval_callback(approval_data: Dict[str, Any]) -> bool:
        """Example approval callback that auto-approves safe commands"""
        logger.info("\n🔒 Approval Request:")
        logger.info(f"Command: {approval_data['command']}")
        logger.info(f"Risk: {approval_data['risk']}")
        logger.info(f"Reasons: {', '.join(approval_data['reasons'])}")

        # In real implementation, this would ask the user
        # For demo, auto-approve moderate risk, deny high risk
        if approval_data["risk"] == "moderate":
            logger.info("✅ Auto-approved (moderate risk)")
            return True
        else:
            logger.info("❌ Auto-denied (high risk)")
            return False

    async def test_commands():
        """Test secure command executor with various risk-level commands."""
        # Create executor with approval callback
        executor = SecureCommandExecutor(
            require_approval_callback=example_approval_callback,
            use_docker_sandbox=False,  # Set to True to test Docker sandboxing
        )

        # Test various commands
        test_cases = [
            "echo 'Hello, secure world!'",  # Safe
            "ls -la /tmp",  # Safe
            "rm test.txt",  # High risk
            "sudo apt update",  # High risk
            "mkdir /tmp/test",  # Moderate risk
            "rm -rf /",  # Forbidden
            "cat /etc/passwd",  # Dangerous pattern
            "echo test > /tmp/safe.txt",  # Safe with redirection
            "curl https://example.com",  # Safe
        ]

        for cmd in test_cases:
            logger.info(f"\n{'='*60}")
            logger.info(f"Testing: {cmd}")
            result = await executor.run_shell_command(cmd)
            logger.info(f"Status: {result['status']}")
            logger.info(f"Security: {result.get('security', {})}")
            if result["stdout"]:
                logger.info(f"Output: {result['stdout'][:100]}...")

        # Show command history
        logger.info(f"\n{'='*60}")
        logger.info("Command History:")
        for entry in executor.get_command_history():
            logger.info(
                f"- {entry['command']}: {entry['risk']} "
                f"(approved: {entry.get('approved', 'N/A')}, "
                f"executed: {entry['executed']})"
            )

    run_or_schedule(test_commands())
