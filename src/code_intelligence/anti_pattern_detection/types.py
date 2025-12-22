# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Anti-Pattern Detection Type Definitions

Contains enums, constants, and pre-compiled regex patterns used throughout
the anti-pattern detection system.

Part of Issue #381 - God Class Refactoring
"""

import re
from enum import Enum


class AntiPatternSeverity(Enum):
    """Severity levels for anti-patterns."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AntiPatternType(Enum):
    """Types of anti-patterns detected."""

    # Bloaters
    GOD_CLASS = "god_class"
    LONG_METHOD = "long_method"
    LONG_PARAMETER_LIST = "long_parameter_list"
    LARGE_FILE = "large_file"
    DEEP_NESTING = "deep_nesting"
    DATA_CLUMPS = "data_clumps"

    # Couplers
    CIRCULAR_DEPENDENCY = "circular_dependency"
    FEATURE_ENVY = "feature_envy"
    MESSAGE_CHAINS = "message_chains"
    INAPPROPRIATE_INTIMACY = "inappropriate_intimacy"

    # Dispensables
    DEAD_CODE = "dead_code"
    DUPLICATE_ABSTRACTION = "duplicate_abstraction"
    LAZY_CLASS = "lazy_class"
    SPECULATIVE_GENERALITY = "speculative_generality"

    # Naming Issues
    INCONSISTENT_NAMING = "inconsistent_naming"
    SINGLE_LETTER_VARIABLE = "single_letter_variable"
    MAGIC_NUMBER = "magic_number"

    # Other
    COMPLEX_CONDITIONAL = "complex_conditional"
    MISSING_DOCSTRING = "missing_docstring"


# ============================================================================
# Pre-compiled regex patterns (Issue #380)
# ============================================================================

# Naming convention patterns
SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
CAMEL_CASE_RE = re.compile(r"^[a-z][a-zA-Z0-9]*$")


# ============================================================================
# Thresholds for detection
# ============================================================================

class Thresholds:
    """Configurable thresholds for anti-pattern detection."""

    # God class detection
    GOD_CLASS_METHOD_THRESHOLD = 20
    GOD_CLASS_LINE_THRESHOLD = 500

    # Parameter limits
    LONG_PARAMETER_THRESHOLD = 5

    # File size limits
    LARGE_FILE_THRESHOLD = 1000

    # Nesting limits
    DEEP_NESTING_THRESHOLD = 4

    # Method limits
    LONG_METHOD_THRESHOLD = 50

    # Chain limits
    MESSAGE_CHAIN_THRESHOLD = 4  # a.b().c().d() = 4 chains

    # Lazy class detection
    LAZY_CLASS_METHOD_THRESHOLD = 2
    LAZY_CLASS_LINE_THRESHOLD = 50

    # Feature envy detection
    FEATURE_ENVY_EXTERNAL_CALL_THRESHOLD = 3

    # Data clumps detection
    DATA_CLUMP_OCCURRENCE_THRESHOLD = 3

    # Complex conditional detection
    COMPLEX_CONDITIONAL_THRESHOLD = 3

    # Magic number detection
    MAGIC_NUMBER_THRESHOLD = 3  # Same number appears more than N times


# ============================================================================
# Default ignore patterns
# ============================================================================

DEFAULT_IGNORE_PATTERNS = [
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "*.pyc",
    "*.pyo",
    "*.egg-info",
    ".tox",
    ".pytest_cache",
]

# Common boilerplate single-letter variables to ignore
ALLOWED_SINGLE_LETTER_VARS = frozenset({
    "i",  # Loop counter
    "j",  # Nested loop counter
    "k",  # Second nested counter
    "n",  # Count/number
    "x",  # Coordinate / generic value
    "y",  # Coordinate
    "z",  # Coordinate
    "e",  # Exception in except blocks
    "_",  # Unused variable
})

# Magic numbers that are commonly acceptable
ALLOWED_MAGIC_NUMBERS = frozenset({
    0, 1, 2, -1, 10, 100, 1000,
    # Common mathematical constants
    0.0, 1.0, 0.5, 2.0,
    # HTTP status codes pattern matching
    200, 201, 204, 400, 401, 403, 404, 500,
})
