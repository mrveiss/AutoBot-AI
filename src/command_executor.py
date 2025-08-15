import asyncio
from typing import Any, Dict

from src.utils.command_utils import execute_shell_command


class CommandExecutor:
    async def run_shell_command(self, command: str) -> Dict[str, Any]:
        """
        Executes a shell command asynchronously.

        Args:
            command: The shell command to execute.

        Returns:
            A dictionary containing stdout, stderr, return code, and status.
        """
        return await execute_shell_command(command)


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
