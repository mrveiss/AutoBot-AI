#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Analyze AutoBot codebase for duplicate functions and generate refactoring recommendations

NOTE: create_command_utils_library (~200 lines) is an ACCEPTABLE EXCEPTION
per Issue #490 - code generator producing library module. Low priority.
"""

import asyncio
import json
import logging
from pathlib import Path

from code_analyzer import CodeAnalyzer

logger = logging.getLogger(__name__)

# Command execution function names to search for (Issue #398: extracted data)
COMMAND_FUNCTION_NAMES = [
    "execute_command",
    "run_command",
    "execute_shell_command",
    "run_shell_command",
    "_run_command",
    "execute_command_with_output",
    "execute_interactive_command",
]


def _get_refactoring_plan() -> dict:
    """Return the refactoring plan for command execution (Issue #398: extracted)."""
    return {
        "phase1": {
            "title": "Consolidate Basic Command Execution",
            "actions": [
                "1. Keep src/utils/command_utils.py as the base implementation",
                "2. Update src/command_executor.py to use command_utils directly",
                "3. Remove duplicate _run_command from agents (use command_utils instead)",
            ],
        },
        "phase2": {
            "title": "Create Command Execution Hierarchy",
            "actions": [
                "1. Base: src/utils/command_utils.py - Basic async command execution",
                "2. Secure: src/secure_command_executor.py - Add security checks",
                "3. Elevated: src/elevation_wrapper.py - Add sudo/elevation support",
            ],
        },
        "phase3": {
            "title": "Standardize Return Format",
            "actions": [
                "1. Use consistent format: {stdout, stderr, return_code, status}",
                "2. Add optional fields: {execution_time, security_metadata}",
                "3. Update all callers to use new format",
            ],
        },
    }


def _find_command_duplicates(results: dict) -> list:
    """Find duplicate groups containing command execution functions (Issue #398: extracted)."""
    command_duplicates = []
    for group in results.get("duplicate_details", []):
        for func in group.get("functions", []):
            if any(
                cmd in func.get("name", "").lower() for cmd in COMMAND_FUNCTION_NAMES
            ):
                command_duplicates.append(group)
                break
    return command_duplicates


def _print_duplicate_analysis(command_duplicates: list) -> None:
    """Print command execution duplicate analysis (Issue #398: extracted)."""
    logger.info("=== Command Execution Duplicate Analysis ===")
    if not command_duplicates:
        logger.info("No command execution duplicates found")
        return

    logger.info(
        f"Found {len(command_duplicates)} groups of duplicate command execution functions:"
    )
    for i, group in enumerate(command_duplicates, 1):
        logger.info(f"{i}. Similarity: {group['similarity_score']:.0%}")
        logger.info(f"   Potential lines saved: {group['estimated_lines_saved']}")
        logger.info("   Duplicate functions:")
        for func in group["functions"]:
            logger.info(f"   - {func['file']}:{func['line_range']} - {func['name']}")


def _print_refactoring_plan(refactoring_plan: dict) -> None:
    """Print the refactoring plan (Issue #398: extracted)."""
    logger.info("=== Refactoring Plan for Command Execution ===")
    for phase, details in refactoring_plan.items():
        logger.info(f"{phase.upper()}: {details['title']}")
        for action in details["actions"]:
            logger.info(f"  {action}")


def _save_analysis_report(
    results: dict, command_duplicates: list, refactoring_plan: dict
) -> Path:
    """Save detailed analysis report to JSON file (Issue #398: extracted)."""
    report_path = Path("code_analysis_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "full_results": results,
                "command_duplicates": command_duplicates,
                "refactoring_plan": refactoring_plan,
            },
            f,
            indent=2,
            default=str,
        )
    return report_path


def _print_migration_outline() -> None:
    """Print migration script outline (Issue #398: extracted)."""
    logger.info("=== Migration Script Outline ===")
    logger.info("1. Update imports in all files:")
    logger.info("   from utils.command_utils import execute_shell_command")
    logger.info("2. Replace function calls:")
    logger.info("   # Before: await self._run_command(cmd)")
    logger.info("   # After:  result = await execute_shell_command(cmd)")
    logger.info("3. Handle return format differences:")
    logger.info(
        "   # Standardize to: result['stdout'], result['stderr'], result['status']"
    )


async def analyze_command_execution_duplicates():
    """Analyze command execution duplicates and generate report (Issue #398: refactored)."""
    logger.info("Starting code analysis for command execution duplicates...")

    analyzer = CodeAnalyzer(use_npu=False)
    results = await analyzer.analyze_codebase(
        root_path=".", patterns=["src/**/*.py", "backend/**/*.py"]
    )

    command_duplicates = _find_command_duplicates(results)
    _print_duplicate_analysis(command_duplicates)

    refactoring_plan = _get_refactoring_plan()
    _print_refactoring_plan(refactoring_plan)

    report_path = _save_analysis_report(results, command_duplicates, refactoring_plan)
    logger.info(f"Detailed report saved to: {report_path}")

    _print_migration_outline()

    return results


async def create_command_utils_library():
    """Create consolidated command utilities library"""

    library_content = '''"""
Consolidated Command Execution Utilities
Provides consistent command execution across AutoBot
"""

import asyncio
import os
import re
import subprocess
from typing import Any, Dict, Optional, List, Union
import logging

logger = logging.getLogger(__name__)


def strip_ansi_codes(text: str) -> str:
    """Remove ANSI escape codes from terminal output."""
    ansi_escape = re.compile(r'\\x1B(?:[@-Z\\\\-_]|\\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)


async def execute_shell_command(
    command: Union[str, List[str]],
    timeout: Optional[int] = 30,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    capture_output: bool = True,
    strip_ansi: bool = True
) -> Dict[str, Any]:
    """
    Execute a shell command asynchronously with consistent error handling.

    Args:
        command: Command to execute (string or list)
        timeout: Command timeout in seconds
        cwd: Working directory
        env: Environment variables
        capture_output: Whether to capture stdout/stderr
        strip_ansi: Whether to strip ANSI codes from output

    Returns:
        Dict with keys: stdout, stderr, return_code, status, execution_time
    """
    import time
    start_time = time.time()

    try:
        # Handle both string and list commands
        if isinstance(command, list):
            shell = False
            cmd = command
        else:
            shell = True
            cmd = command

        # Create subprocess
        process = await asyncio.create_subprocess_shell(
            cmd if shell else ' '.join(cmd),
            stdout=asyncio.subprocess.PIPE if capture_output else None,
            stderr=asyncio.subprocess.PIPE if capture_output else None,
            cwd=cwd,
            env=env
        )

        # Wait for completion with timeout
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return {
                "stdout": "",
                "stderr": f"Command timed out after {timeout} seconds",
                "return_code": -1,
                "status": "timeout",
                "execution_time": time.time() - start_time
            }

        # Process output
        stdout_str = stdout.decode('utf-8', errors='replace').strip() if stdout else ""
        stderr_str = stderr.decode('utf-8', errors='replace').strip() if stderr else ""

        if strip_ansi:
            stdout_str = strip_ansi_codes(stdout_str)
            stderr_str = strip_ansi_codes(stderr_str)

        return_code = process.returncode
        status = "success" if return_code == 0 else "error"

        return {
            "stdout": stdout_str,
            "stderr": stderr_str,
            "return_code": return_code,
            "status": status,
            "execution_time": time.time() - start_time
        }

    except FileNotFoundError:
        return {
            "stdout": "",
            "stderr": f"Command not found: {command}",
            "return_code": 127,
            "status": "error",
            "execution_time": time.time() - start_time
        }
    except Exception as e:
        logger.error(f"Command execution failed: {e}")
        return {
            "stdout": "",
            "stderr": f"Error executing command: {e}",
            "return_code": 1,
            "status": "error",
            "execution_time": time.time() - start_time
        }


def execute_shell_command_sync(
    command: Union[str, List[str]],
    timeout: Optional[int] = 30,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    capture_output: bool = True,
    strip_ansi: bool = True
) -> Dict[str, Any]:
    """
    Synchronous version of execute_shell_command for non-async contexts.

    Returns same format as async version.
    """
    import time
    start_time = time.time()

    try:
        result = subprocess.run(
            command,
            shell=isinstance(command, str),
            capture_output=capture_output,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=env
        )

        stdout_str = result.stdout.strip() if result.stdout else ""
        stderr_str = result.stderr.strip() if result.stderr else ""

        if strip_ansi:
            stdout_str = strip_ansi_codes(stdout_str)
            stderr_str = strip_ansi_codes(stderr_str)

        return {
            "stdout": stdout_str,
            "stderr": stderr_str,
            "return_code": result.returncode,
            "status": "success" if result.returncode == 0 else "error",
            "execution_time": time.time() - start_time
        }

    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"Command timed out after {timeout} seconds",
            "return_code": -1,
            "status": "timeout",
            "execution_time": time.time() - start_time
        }
    except FileNotFoundError:
        return {
            "stdout": "",
            "stderr": f"Command not found: {command}",
            "return_code": 127,
            "status": "error",
            "execution_time": time.time() - start_time
        }
    except Exception as e:
        logger.error(f"Command execution failed: {e}")
        return {
            "stdout": "",
            "stderr": f"Error executing command: {e}",
            "return_code": 1,
            "status": "error",
            "execution_time": time.time() - start_time
        }


# Aliases for backward compatibility
run_command = execute_shell_command
run_command_sync = execute_shell_command_sync
'''

    # Save the consolidated library
    lib_path = Path("src/utils/command_utils_consolidated.py")
    lib_path.write_text(library_content, encoding="utf-8")
    logger.info(f"Created consolidated command utilities at: {lib_path}")


async def main():
    """Run the duplicate analysis"""

    # Analyze duplicates
    await analyze_command_execution_duplicates()

    # Create consolidated library
    await create_command_utils_library()

    logger.info("=== Analysis Complete ===")
    logger.info("Next steps:")
    logger.info("1. Review code_analysis_report.json for detailed findings")
    logger.info("2. Implement refactoring plan phase by phase")
    logger.info("3. Run tests after each phase to ensure nothing breaks")


if __name__ == "__main__":
    asyncio.run(main())
