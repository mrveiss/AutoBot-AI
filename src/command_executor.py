import asyncio
import logging
from typing import Any, Dict

from src.constants.network_constants import NetworkConstants
from src.secure_command_executor import (
    CommandRisk,
    SecureCommandExecutor,
    SecurityPolicy,
)
from src.utils.command_utils import execute_shell_command

logger = logging.getLogger(__name__)

# SECURITY WARNING: This class has been converted to use secure command execution
# All command execution now goes through security validation and auditing


class CommandExecutor:
    """DEPRECATED: Use SecureCommandExecutor directly for better security control

    This wrapper maintains backward compatibility while enforcing security.
    """

    def __init__(self):
        logger.warning(
            "CommandExecutor is deprecated. Use SecureCommandExecutor directly for better security control."
        )
        # Initialize with high security by default
        self._secure_executor = SecureCommandExecutor(
            policy=SecurityPolicy(),
            use_docker_sandbox=True,  # Enable sandboxing by default
        )

    async def run_shell_command(self, command: str) -> Dict[str, Any]:
        """
        Executes a shell command asynchronously with security validation.

        BREAKING CHANGE: Commands are now validated and may be blocked for security.
        High-risk commands will be rejected unless explicit approval is configured.

        Args:
            command: The shell command to execute.

        Returns:
            A dictionary containing stdout, stderr, return code, status, and security info.
        """
        logger.info(
            f"SECURITY: Executing command through secure wrapper: {command[:50]}..."
        )

        # Use secure execution
        result = await self._secure_executor.run_shell_command(command)

        # Log security events
        security_info = result.get("security", {})
        if security_info.get("blocked"):
            logger.warning(
                f"SECURITY: Command blocked - {command} - Reason: {security_info.get('reasons')}"
            )
        elif security_info.get("sandboxed"):
            logger.info(f"SECURITY: Command executed in sandbox - {command}")

        return result


# Example Usage (for testing)
if __name__ == "__main__":

    async def main():
        executor = CommandExecutor()

        # Test a successful command
        print("--- Testing successful command ---")
        result = await executor.run_shell_command("echo 'Hello, world!'")
        print(result)

        # Test a command with error
        print("\n--- Testing command with error ---")
        result = await executor.run_shell_command("ls non_existent_directory")
        print(result)

        # Test a command not found
        print("\n--- Testing command not found ---")
        result = await executor.run_shell_command("non_existent_command arg1 arg2")
        print(result)

    asyncio.run(main())
