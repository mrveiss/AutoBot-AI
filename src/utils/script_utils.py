#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Shared utility functions for AutoBot scripts
Eliminates code duplication across deployment, backup, and monitoring scripts
"""

import sys
from datetime import datetime
from typing import FrozenSet, Optional

# Issue #380: Module-level frozenset for confirmation responses
_CONFIRM_TRUE_RESPONSES: FrozenSet[str] = frozenset({"y", "yes", "true", "1"})


class ScriptFormatter:
    """Common formatting utilities for AutoBot scripts"""

    @staticmethod
    def print_header(title: str, width: int = 60):
        """
        Print formatted header for script sections.

        Args:
            title: The title to display
            width: Width of the header (default: 60)
        """
        print(f"\n{'=' * width}")
        print(f"  {title}")
        print("=" * width)

    @staticmethod
    def print_step(step: str, status: str = "info"):
        """
        Print formatted step with status.

        Args:
            step: The step description
            status: Status level (info, success, warning, error)
        """
        status_symbols = {
            "info": "📋",
            "success": "✅",
            "warning": "⚠️",
            "error": "❌",
            "running": "🔄",
        }

        symbol = status_symbols.get(status, "📋")
        print(f"{symbol} {step}")

    @staticmethod
    def print_section(title: str, items: list, width: int = 60):
        """
        Print a formatted section with items.

        Args:
            title: Section title
            items: List of items to display
            width: Width of the section
        """
        print(f"\n{'-' * width}")
        print(f"  {title}")
        print(f"{'-' * width}")
        for item in items:
            print(f"   • {item}")

    @staticmethod
    def print_config_summary(config_data: dict, title: str = "Configuration Summary"):
        """
        Print formatted configuration summary.

        Args:
            config_data: Dictionary of configuration items
            title: Title for the summary
        """
        ScriptFormatter.print_header(title)
        for key, value in config_data.items():
            print(f"   {key}: {value}")

    @staticmethod
    def print_error(message: str, exit_code: Optional[int] = None):
        """
        Print formatted error message and optionally exit.

        Args:
            message: Error message
            exit_code: If provided, exit with this code
        """
        print(f"❌ ERROR: {message}", file=sys.stderr)
        if exit_code is not None:
            sys.exit(exit_code)

    @staticmethod
    def print_success(message: str):
        """
        Print formatted success message.

        Args:
            message: Success message
        """
        print(f"✅ SUCCESS: {message}")

    @staticmethod
    def print_warning(message: str):
        """
        Print formatted warning message.

        Args:
            message: Warning message
        """
        print(f"⚠️  WARNING: {message}")

    @staticmethod
    def print_timestamp():
        """Print current timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"⏰ {timestamp}")

    @staticmethod
    def print_separator(char: str = "-", width: int = 60):
        """
        Print a separator line.

        Args:
            char: Character to use for separator
            width: Width of the separator
        """
        print(char * width)


class ProgressIndicator:
    """Progress indication utilities for long-running operations"""

    def __init__(self, total_steps: int, description: str = "Processing"):
        """Initialize progress indicator with total steps and description."""
        self.total_steps = total_steps
        self.current_step = 0
        self.description = description

    def step(self, message: str = ""):
        """Advance progress by one step"""
        self.current_step += 1
        percentage = (self.current_step / self.total_steps) * 100
        progress_bar = "█" * int(percentage // 4) + "░" * (25 - int(percentage // 4))

        step_info = f" - {message}" if message else ""
        progress = f"{percentage:.1f}% ({self.current_step}/{self.total_steps})"
        print(
            f"\r🔄 {self.description}: [{progress_bar}] {progress}{step_info}",
            end="",
        )

        if self.current_step >= self.total_steps:
            print()  # New line when complete

    def complete(self, message: str = "Completed"):
        """Mark progress as complete"""
        print(f"\n✅ {message}")


def validate_required_args(args: dict, required: list) -> bool:
    """
    Validate that required arguments are present.

    Args:
        args: Dictionary of arguments
        required: List of required argument names

    Returns:
        True if all required args are present
    """
    missing = [arg for arg in required if not args.get(arg)]
    if missing:
        ScriptFormatter.print_error(f"Missing required arguments: {', '.join(missing)}")
        return False
    return True


def confirm_action(message: str, default: bool = False) -> bool:
    """
    Ask user for confirmation.

    Args:
        message: Confirmation message
        default: Default value if user just presses Enter

    Returns:
        True if user confirms
    """
    default_str = "Y/n" if default else "y/N"
    response = input(f"❓ {message} ({default_str}): ").strip().lower()

    if not response:
        return default

    return response in _CONFIRM_TRUE_RESPONSES


# Legacy compatibility - these functions maintain the original interface
# for existing scripts that import them directly


def print_header(title: str):
    """Legacy compatibility function"""
    ScriptFormatter.print_header(title)


def print_step(step: str, status: str = "info"):
    """Legacy compatibility function"""
    ScriptFormatter.print_step(step, status)


def print_error(message: str, exit_code: Optional[int] = None):
    """Legacy compatibility function"""
    ScriptFormatter.print_error(message, exit_code)


def print_success(message: str):
    """Legacy compatibility function"""
    ScriptFormatter.print_success(message)


def print_warning(message: str):
    """Legacy compatibility function"""
    ScriptFormatter.print_warning(message)
