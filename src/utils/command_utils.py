# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import asyncio
import re
from datetime import datetime
from typing import Any, Dict


def strip_ansi_codes(text: str) -> str:
    """Removes ANSI escape codes from a string."""
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    return ansi_escape.sub("", text)


def get_timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.now().isoformat()


async def execute_shell_command(command: str) -> Dict[str, Any]:
    """
    Executes a shell command asynchronously and cleans the output.

    Args:
        command: The shell command to execute.

    Returns:
        A dictionary containing cleaned stdout, stderr, return code, and status.
    """
    try:
        process = await asyncio.create_subprocess_shell(
            command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        stdout_str = strip_ansi_codes(stdout.decode()).strip()
        stderr_str = strip_ansi_codes(stderr.decode()).strip()
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
