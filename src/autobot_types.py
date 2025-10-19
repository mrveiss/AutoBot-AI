"""
Shared type definitions for AutoBot
"""

from enum import Enum

from src.constants.network_constants import NetworkConstants


class TaskComplexity(Enum):
    SIMPLE = "simple"  # Regular conversation with Knowledge Base integration
    COMPLEX = "complex"  # Requires tools, research, or system actions

    # Legacy values for backward compatibility (map to COMPLEX)
    RESEARCH = "complex"
    INSTALL = "complex"
    SECURITY_SCAN = "complex"
