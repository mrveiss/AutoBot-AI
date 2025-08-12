"""
Shared type definitions for AutoBot
"""

from enum import Enum


class TaskComplexity(Enum):
    SIMPLE = "simple"  # Single agent can handle
    RESEARCH = "research"  # Requires web research
    INSTALL = "install"  # Requires system commands
    COMPLEX = "complex"  # Multi-agent coordination needed
    SECURITY_SCAN = "security_scan"  # Security scanning workflow
