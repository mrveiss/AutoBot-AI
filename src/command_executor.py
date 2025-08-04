import os
import asyncio
import subprocess
from typing import Dict, Any


class CommandExecutor:
    async def run_shell_command(self, command: str) -> Dict[str, Any]:
        """
        Executes a shell command asynchronously.

        Args:
            command: The shell command to execute.

        Returns:
            A dictionary containing stdout, stderr, return code, and status.
        """
        try:
            process = await asyncio.create_subprocess_shell(
                command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            stdout_str = stdout.decode().strip()
            stderr_str = stderr.decode().strip()
            return_code = process.returncode

            status = "success" if return_code == 0 else "error"

            return {
                "stdout": stdout_str,
                "stderr": stderr_str,
                "return_code": return_code,
                "status": status,
            }
        except FileNotFoundError:
            return {
                "stdout": "",
                "stderr": f"Command not found: {command}",
                "return_code": 127,  # Common return code for command not found
                "status": "error",
            }
        except Exception as e:
            return {
                "stdout": "",
                "stderr": f"Error executing command: {e}",
                "return_code": 1,  # Generic error code
                "status": "error",
            }


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
