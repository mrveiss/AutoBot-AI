# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Security module for AutoBot.
Provides secure command validation and other security utilities.
"""

from .command_validator import CommandValidator, get_command_validator

__all__ = ["CommandValidator", "get_command_validator"]
