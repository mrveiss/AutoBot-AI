# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
KB Librarian Types - Constants and keyword sets for knowledge base operations.

Extracted from enhanced_kb_librarian.py as part of Issue #381 god class refactoring.
"""

# Performance optimization: O(1) lookup for keyword checks (Issue #326)
REQUIREMENT_KEYWORDS = {"require", "depend", "need", "prerequisite"}
SYNTAX_PATTERNS = {"Usage:", "Syntax:", "SYNOPSIS", "usage:"}
OUTPUT_FORMAT_KEYWORDS = {"output", "format", "result", "report"}
ADVANCED_FEATURE_KEYWORDS = {"feature", "capability", "support", "advanced"}
ERROR_CODE_PATTERNS = {"error", "exit code", "return code"}
PROBLEM_KEYWORDS = {"problem", "issue", "error", "fail"}
SOLUTION_KEYWORDS = {"solution", "fix", "resolve"}
COMMON_CLI_TOOLS = {"grep", "awk", "sed", "find", "xargs"}
SECURITY_KEYWORDS = {"secure", "safe", "recommend", "best practice"}
OFFICIAL_DOC_DOMAINS = {"github.com", "docs.", "man7.org", ".org"}
LIMITATION_KEYWORDS = {"limit", "cannot", "not support", "restriction"}
PERFORMANCE_KEYWORDS = {"performance", "speed", "memory", "cpu", "slow", "fast"}

# Issue #380: Module-level frozenset for text section handling
TEXT_SECTIONS = frozenset({"installation", "usage"})

# Issue #380: Module-level tuple for tool info optional fields (used in iteration)
TOOL_INFO_OPTIONAL_FIELDS = (
    "purpose",
    "installation",
    "requirements",
    "package_name",
    "usage",
    "syntax",
    "output_formats",
    "advanced_usage",
    "features",
    "troubleshooting",
    "error_codes",
    "integrations",
    "security_notes",
    "documentation_url",
    "verified",
    "limitations",
    "performance",
)

INSTALLATION_COMMANDS = {
    "apt install",
    "apt-get install",
    "yum install",
    "dnf install",
    "pacman -S",
    "brew install",
    "pip install",
    "npm install",
}

COMMAND_OPERATORS = {"-", "--", "|", ">", "<"}
FEATURE_INDICATORS = {"feature", "support", "can", "allow", "enable"}
TOOL_NAME_CHARS = {"-", "_"}  # Characters that often appear in tool names

__all__ = [
    "REQUIREMENT_KEYWORDS",
    "SYNTAX_PATTERNS",
    "OUTPUT_FORMAT_KEYWORDS",
    "ADVANCED_FEATURE_KEYWORDS",
    "ERROR_CODE_PATTERNS",
    "PROBLEM_KEYWORDS",
    "SOLUTION_KEYWORDS",
    "COMMON_CLI_TOOLS",
    "SECURITY_KEYWORDS",
    "OFFICIAL_DOC_DOMAINS",
    "LIMITATION_KEYWORDS",
    "PERFORMANCE_KEYWORDS",
    "TEXT_SECTIONS",
    "TOOL_INFO_OPTIONAL_FIELDS",
    "INSTALLATION_COMMANDS",
    "COMMAND_OPERATORS",
    "FEATURE_INDICATORS",
    "TOOL_NAME_CHARS",
]
