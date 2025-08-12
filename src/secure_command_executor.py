"""
Secure Command Executor with Sandboxing and Permission Controls
Implements security measures to prevent arbitrary command execution
"""

import asyncio
import os
import re
import shlex
import logging
from typing import Any, Dict, List, Optional, Set
from src.utils.command_utils import execute_shell_command
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class CommandRisk(Enum):
    """Risk levels for commands"""
    SAFE = "safe"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"
    FORBIDDEN = "forbidden"


class SecurityPolicy:
    """Security policy for command execution"""
    
    def __init__(self):
        # Safe commands that can run without approval
        self.safe_commands = {
            "echo", "date", "pwd", "whoami", "hostname", "uname",
            "cat", "head", "tail", "wc", "sort", "uniq", "grep",
            "find", "ls", "tree", "which", "env", "printenv",
            "ps", "top", "htop", "df", "du", "free", "uptime",
            "ping", "curl", "wget", "git", "npm", "python", "pip"
        }
        
        # Commands that need approval for certain arguments
        self.moderate_commands = {
            "cp", "mv", "mkdir", "touch", "chmod", "chown",
            "tar", "zip", "unzip", "gzip", "gunzip",
            "sed", "awk", "cut", "paste", "join"
        }
        
        # High-risk commands that always need approval
        self.high_risk_commands = {
            "rm", "rmdir", "dd", "mkfs", "fdisk", "parted",
            "mount", "umount", "chroot", "sudo", "su",
            "systemctl", "service", "apt", "apt-get", "dpkg",
            "yum", "dnf", "zypper", "pacman"
        }
        
        # Forbidden commands that should never run
        self.forbidden_commands = {
            "shutdown", "reboot", "halt", "poweroff",
            "init", "telinit", "kill", "killall", "pkill"
        }
        
        # Dangerous patterns in arguments
        self.dangerous_patterns = [
            r"rm\s+-rf\s+/",  # rm -rf /
            r">\s*/dev/sd[a-z]",  # Overwrite disk
            r"dd\s+.*of=/dev/",  # dd to device
            r"/etc/passwd",  # Password file
            r"/etc/shadow",  # Shadow file
            r":(){ :|:& };:",  # Fork bomb
            r"\$\(.*\)",  # Command substitution
            r"`.*`",  # Backtick substitution
            r";\s*rm\s+-rf",  # Command chaining with rm
            r"&&\s*rm\s+-rf",  # Conditional rm
            r"\|\s*rm\s+-rf",  # Piped to rm
        ]
        
        # Allowed directories for file operations
        self.allowed_paths = [
            Path.home(),  # User home directory
            Path("/tmp"),  # Temporary directory
            Path("/var/tmp"),  # Var temporary
            Path.cwd(),  # Current working directory
        ]
        
        # File extensions that can be modified
        self.allowed_extensions = {
            ".txt", ".log", ".json", ".yaml", ".yml", ".md",
            ".py", ".js", ".ts", ".jsx", ".tsx", ".vue",
            ".html", ".css", ".scss", ".sass",
            ".sh", ".bash", ".zsh",
            ".conf", ".cfg", ".ini", ".env",
            ".csv", ".tsv", ".xml"
        }


class SecureCommandExecutor:
    """
    Secure command executor with sandboxing and permission controls
    """
    
    def __init__(self, policy: Optional[SecurityPolicy] = None,
                 require_approval_callback=None,
                 use_docker_sandbox: bool = False):
        """
        Initialize secure command executor
        
        Args:
            policy: Security policy to use (default: SecurityPolicy())
            require_approval_callback: Async callback function for user approval
            use_docker_sandbox: Whether to execute commands in Docker container
        """
        self.policy = policy or SecurityPolicy()
        self.require_approval_callback = require_approval_callback
        self.use_docker_sandbox = use_docker_sandbox
        self.docker_image = "autobot-sandbox:latest"
        
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
        """Check command for dangerous patterns"""
        found_patterns = []
        for pattern in self.policy.dangerous_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                found_patterns.append(pattern)
        return found_patterns
    
    def _check_path_access(self, command: str) -> bool:
        """Check if file operations are within allowed paths"""
        # This is a simplified check - in production, parse command properly
        # to extract all file paths
        for allowed_path in self.policy.allowed_paths:
            if str(allowed_path) in command:
                return True
        return False
    
    def assess_command_risk(self, command: str) -> tuple[CommandRisk, List[str]]:
        """
        Assess the risk level of a command
        
        Returns:
            (risk_level, list_of_reasons)
        """
        reasons = []
        base_command = self._extract_command_name(command)
        
        # Check for empty or malformed commands
        if not base_command:
            return CommandRisk.FORBIDDEN, ["Empty or malformed command"]
        
        # Check dangerous patterns first
        dangerous_patterns = self._check_dangerous_patterns(command)
        if dangerous_patterns:
            reasons.extend([f"Dangerous pattern: {p}" for p in dangerous_patterns])
            return CommandRisk.FORBIDDEN, reasons
        
        # Check command categories
        if base_command in self.policy.forbidden_commands:
            reasons.append(f"Forbidden command: {base_command}")
            return CommandRisk.FORBIDDEN, reasons
        
        if base_command in self.policy.high_risk_commands:
            reasons.append(f"High-risk command: {base_command}")
            return CommandRisk.HIGH, reasons
        
        if base_command in self.policy.moderate_commands:
            reasons.append(f"Moderate-risk command: {base_command}")
            # Check if it involves system paths
            if any(path in command for path in ["/etc", "/usr", "/bin", "/sbin", "/lib"]):
                reasons.append("Operates on system paths")
                return CommandRisk.HIGH, reasons
            return CommandRisk.MODERATE, reasons
        
        if base_command in self.policy.safe_commands:
            # Even safe commands can be risky with certain arguments
            if "sudo" in command or command.startswith("sudo"):
                reasons.append("Uses sudo elevation")
                return CommandRisk.HIGH, reasons
            
            # Check for output redirection to sensitive files
            if ">" in command or ">>" in command:
                if any(sensitive in command for sensitive in ["/etc/", "/boot/", "/sys/"]):
                    reasons.append("Redirects to sensitive location")
                    return CommandRisk.HIGH, reasons
            
            return CommandRisk.SAFE, ["Safe command"]
        
        # Unknown command - treat as moderate risk
        reasons.append(f"Unknown command: {base_command}")
        return CommandRisk.MODERATE, reasons
    
    async def _request_approval(self, command: str, risk: CommandRisk, 
                               reasons: List[str]) -> bool:
        """Request user approval for command execution"""
        if self.require_approval_callback:
            approval_data = {
                "command": command,
                "risk": risk.value,
                "reasons": reasons,
                "timestamp": asyncio.get_event_loop().time()
            }
            return await self.require_approval_callback(approval_data)
        
        # If no callback, log and deny by default for safety
        logger.warning(f"No approval callback set. Denying command: {command}")
        return False
    
    def _build_docker_command(self, command: str) -> str:
        """Build Docker command for sandboxed execution"""
        # Create a minimal sandbox container
        docker_cmd = [
            "docker", "run",
            "--rm",  # Remove container after execution
            "--read-only",  # Read-only root filesystem
            "--network", "none",  # No network access
            "--memory", "512m",  # Memory limit
            "--cpus", "1.0",  # CPU limit
            "--user", "1000:1000",  # Non-root user
            "-v", f"{os.getcwd()}:/workspace:ro",  # Mount current dir read-only
            "-w", "/workspace",
            self.docker_image,
            "sh", "-c", command
        ]
        return " ".join(docker_cmd)
    
    async def run_shell_command(self, command: str, 
                               force_approval: bool = False) -> Dict[str, Any]:
        """
        Securely execute a shell command with risk assessment and sandboxing
        
        Args:
            command: The shell command to execute
            force_approval: Force user approval regardless of risk level
            
        Returns:
            Dictionary containing execution results and security info
        """
        # Assess command risk
        risk, reasons = self.assess_command_risk(command)
        
        # Log command attempt
        log_entry = {
            "command": command,
            "risk": risk.value,
            "reasons": reasons,
            "timestamp": asyncio.get_event_loop().time(),
            "approved": False,
            "executed": False
        }
        
        # Check if command is forbidden
        if risk == CommandRisk.FORBIDDEN:
            logger.error(f"Forbidden command blocked: {command}")
            log_entry["error"] = "Command forbidden by security policy"
            self.command_history.append(log_entry)
            return {
                "stdout": "",
                "stderr": f"Command forbidden: {'; '.join(reasons)}",
                "return_code": 1,
                "status": "error",
                "security": {
                    "risk": risk.value,
                    "reasons": reasons,
                    "blocked": True
                }
            }
        
        # Check if approval is needed
        needs_approval = force_approval or risk in [CommandRisk.HIGH, CommandRisk.MODERATE]
        
        if needs_approval:
            approved = await self._request_approval(command, risk, reasons)
            log_entry["approved"] = approved
            
            if not approved:
                logger.warning(f"Command denied by user: {command}")
                log_entry["error"] = "User denied execution"
                self.command_history.append(log_entry)
                return {
                    "stdout": "",
                    "stderr": "Command execution denied by user",
                    "return_code": 1,
                    "status": "error",
                    "security": {
                        "risk": risk.value,
                        "reasons": reasons,
                        "blocked": True
                    }
                }
        
        # Prepare command for execution
        if self.use_docker_sandbox and risk != CommandRisk.SAFE:
            # Use Docker sandbox for non-safe commands
            actual_command = self._build_docker_command(command)
            logger.info(f"Executing in Docker sandbox: {command}")
        else:
            actual_command = command
        
        # Execute command
        try:
            result = await execute_shell_command(actual_command)
            
            log_entry["executed"] = True
            log_entry["return_code"] = result["return_code"]
            self.command_history.append(log_entry)
            
            result["security"] = {
                "risk": risk.value,
                "reasons": reasons,
                "sandboxed": self.use_docker_sandbox and risk != CommandRisk.SAFE,
                "approved": needs_approval
            }
            return result
            
        except asyncio.TimeoutError:
            logger.error(f"Command timed out: {command}")
            log_entry["error"] = "Command timed out"
            self.command_history.append(log_entry)
            return {
                "stdout": "",
                "stderr": "Command execution timed out after 5 minutes",
                "return_code": 124,  # Standard timeout exit code
                "status": "error",
                "security": {
                    "risk": risk.value,
                    "reasons": reasons,
                    "timeout": True
                }
            }
        except Exception as e:
            logger.error(f"Command execution error: {e}")
            log_entry["error"] = str(e)
            self.command_history.append(log_entry)
            return {
                "stdout": "",
                "stderr": f"Error executing command: {e}",
                "return_code": 1,
                "status": "error",
                "security": {
                    "risk": risk.value,
                    "reasons": reasons,
                    "error": str(e)
                }
            }
    
    def get_command_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent command history for audit purposes"""
        return self.command_history[-limit:]
    
    def clear_history(self):
        """Clear command history"""
        self.command_history.clear()


# Example usage and testing
if __name__ == "__main__":
    async def example_approval_callback(approval_data: Dict[str, Any]) -> bool:
        """Example approval callback that auto-approves safe commands"""
        print(f"\n🔒 Approval Request:")
        print(f"Command: {approval_data['command']}")
        print(f"Risk: {approval_data['risk']}")
        print(f"Reasons: {', '.join(approval_data['reasons'])}")
        
        # In real implementation, this would ask the user
        # For demo, auto-approve moderate risk, deny high risk
        if approval_data['risk'] == 'moderate':
            print("✅ Auto-approved (moderate risk)")
            return True
        else:
            print("❌ Auto-denied (high risk)")
            return False
    
    async def test_commands():
        # Create executor with approval callback
        executor = SecureCommandExecutor(
            require_approval_callback=example_approval_callback,
            use_docker_sandbox=False  # Set to True to test Docker sandboxing
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
            print(f"\n{'='*60}")
            print(f"Testing: {cmd}")
            result = await executor.run_shell_command(cmd)
            print(f"Status: {result['status']}")
            print(f"Security: {result.get('security', {})}")
            if result['stdout']:
                print(f"Output: {result['stdout'][:100]}...")
        
        # Show command history
        print(f"\n{'='*60}")
        print("Command History:")
        for entry in executor.get_command_history():
            print(f"- {entry['command']}: {entry['risk']} "
                  f"(approved: {entry.get('approved', 'N/A')}, "
                  f"executed: {entry['executed']})")
    
    asyncio.run(test_commands())
