#!/usr/bin/env python3
"""
Analyze AutoBot codebase for duplicate functions and generate refactoring recommendations
"""

import asyncio
import json
from pathlib import Path

from src.code_analyzer import CodeAnalyzer


async def analyze_command_execution_duplicates():
    """Specifically analyze command execution related duplicates"""
    
    print("Starting code analysis for command execution duplicates...")
    
    analyzer = CodeAnalyzer(use_npu=False)  # NPU not needed for this analysis
    
    # Run fresh analysis
    results = await analyzer.analyze_codebase(
        root_path=".",
        patterns=["src/**/*.py", "backend/**/*.py"]
    )
    
    # Filter for command execution related functions
    command_functions = [
        "execute_command", "run_command", "execute_shell_command",
        "run_shell_command", "_run_command", "execute_command_with_output",
        "execute_interactive_command"
    ]
    
    print("\n=== Command Execution Duplicate Analysis ===\n")
    
    # Find command execution duplicates
    command_duplicates = []
    for group in results['duplicate_details']:
        for func in group['functions']:
            if any(cmd in func['name'].lower() for cmd in command_functions):
                command_duplicates.append(group)
                break
    
    if command_duplicates:
        print(f"Found {len(command_duplicates)} groups of duplicate command execution functions:\n")
        
        for i, group in enumerate(command_duplicates, 1):
            print(f"{i}. Similarity: {group['similarity_score']:.0%}")
            print(f"   Potential lines saved: {group['estimated_lines_saved']}")
            print("   Duplicate functions:")
            for func in group['functions']:
                print(f"   - {func['file']}:{func['line_range']} - {func['name']}")
            print()
    
    # Generate refactoring plan
    print("\n=== Refactoring Plan for Command Execution ===\n")
    
    refactoring_plan = {
        "phase1": {
            "title": "Consolidate Basic Command Execution",
            "actions": [
                "1. Keep src/utils/command_utils.py as the base implementation",
                "2. Update src/command_executor.py to use command_utils directly",
                "3. Remove duplicate _run_command from agents (use command_utils instead)"
            ]
        },
        "phase2": {
            "title": "Create Command Execution Hierarchy",
            "actions": [
                "1. Base: src/utils/command_utils.py - Basic async command execution",
                "2. Secure: src/secure_command_executor.py - Add security checks",
                "3. Elevated: src/elevation_wrapper.py - Add sudo/elevation support"
            ]
        },
        "phase3": {
            "title": "Standardize Return Format",
            "actions": [
                "1. Use consistent format: {stdout, stderr, return_code, status}",
                "2. Add optional fields: {execution_time, security_metadata}",
                "3. Update all callers to use new format"
            ]
        }
    }
    
    for phase, details in refactoring_plan.items():
        print(f"{phase.upper()}: {details['title']}")
        for action in details['actions']:
            print(f"  {action}")
        print()
    
    # Save detailed report
    report_path = Path("code_analysis_report.json")
    with open(report_path, 'w') as f:
        json.dump({
            "full_results": results,
            "command_duplicates": command_duplicates,
            "refactoring_plan": refactoring_plan
        }, f, indent=2, default=str)
    
    print(f"\nDetailed report saved to: {report_path}")
    
    # Generate migration script outline
    print("\n=== Migration Script Outline ===\n")
    print("1. Update imports in all files:")
    print("   from src.utils.command_utils import execute_shell_command")
    print("\n2. Replace function calls:")
    print("   # Before: await self._run_command(cmd)")
    print("   # After:  result = await execute_shell_command(cmd)")
    print("\n3. Handle return format differences:")
    print("   # Standardize to: result['stdout'], result['stderr'], result['status']")
    
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
    lib_path.write_text(library_content)
    print(f"Created consolidated command utilities at: {lib_path}")


async def main():
    """Run the duplicate analysis"""
    
    # Analyze duplicates
    results = await analyze_command_execution_duplicates()
    
    # Create consolidated library
    await create_command_utils_library()
    
    print("\n=== Analysis Complete ===")
    print("Next steps:")
    print("1. Review code_analysis_report.json for detailed findings")
    print("2. Implement refactoring plan phase by phase")
    print("3. Run tests after each phase to ensure nothing breaks")


if __name__ == "__main__":
    asyncio.run(main())