# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
KB Librarian Package - Focused modules for knowledge base tool management.

Refactored from enhanced_kb_librarian.py (1,465 lines) as part of Issue #381.

Package Structure:
- types.py: Constants and keyword sets (70 lines)
- text_extraction.py: TextExtractor class (270 lines)
- formatters.py: ToolInfoFormatter class (260 lines)
- processors.py: ResultProcessor, ToolInfoData, ResearchResultsProcessor (280 lines)
- parsers.py: InstructionParser class (100 lines)
- librarian.py: EnhancedKBLibrarian facade (400 lines)

Total: ~1,380 lines across 6 focused modules
Original: 1,465 lines in single god class
"""

from .formatters import ToolInfoFormatter
from .librarian import EnhancedKBLibrarian
from .parsers import InstructionParser
from .processors import ResearchResultsProcessor, ResultProcessor, ToolInfoData
from .text_extraction import TextExtractor
from .types import (
    ADVANCED_FEATURE_KEYWORDS,
    COMMAND_OPERATORS,
    COMMON_CLI_TOOLS,
    ERROR_CODE_PATTERNS,
    FEATURE_INDICATORS,
    INSTALLATION_COMMANDS,
    LIMITATION_KEYWORDS,
    OFFICIAL_DOC_DOMAINS,
    OUTPUT_FORMAT_KEYWORDS,
    PERFORMANCE_KEYWORDS,
    PROBLEM_KEYWORDS,
    REQUIREMENT_KEYWORDS,
    SECURITY_KEYWORDS,
    SOLUTION_KEYWORDS,
    SYNTAX_PATTERNS,
    TEXT_SECTIONS,
    TOOL_INFO_OPTIONAL_FIELDS,
    TOOL_NAME_CHARS,
)

__all__ = [
    # Main class
    "EnhancedKBLibrarian",
    # Helper classes
    "TextExtractor",
    "ToolInfoFormatter",
    "ResultProcessor",
    "ResearchResultsProcessor",
    "ToolInfoData",
    "InstructionParser",
    # Constants
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
