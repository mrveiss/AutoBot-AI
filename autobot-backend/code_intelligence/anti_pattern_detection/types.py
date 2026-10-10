# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Anti-Pattern Detection Type Definitions

Contains enums, constants, and pre-compiled regex patterns used throughout
the anti-pattern detection system.

Part of Issue #381 - God Class Refactoring
"""

import re

from autobot_shared.status_enums import Severity

# AntiPatternType is deliberately NOT defined here.  GH#6757 made
# ``code_analysis.src.anti_pattern_detector.AntiPatternType`` the canonical SSOT and
# merged this package's members into it, but this module kept a diverged 19-member
# copy -- so the name resolved to two distinct Enum classes depending on the import
# path (the ``anti_pattern_detector`` facade vs this package) and members compared
# unequal across that boundary.  Re-exported so ``from .types import AntiPatternType``
# keeps working for every detector in this package.
from code_analysis.src.anti_pattern_detector import AntiPatternType  # noqa: F401

#: An exact subset of the canonical ladder, so an alias rather than a class (#18098).
#: Safe to alias because every severity distribution built from this is built from the
#: values actually OBSERVED in results, never by iterating the member set -- so the
#: canonical's ten members do not add five always-zero keys to a response. Four of its
#: former siblings do iterate, and are deliberately left alone; see the issue.
AntiPatternSeverity = Severity


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
ALLOWED_SINGLE_LETTER_VARS = frozenset(
    {
        "i",  # Loop counter
        "j",  # Nested loop counter
        "k",  # Second nested counter
        "n",  # Count/number
        "x",  # Coordinate / generic value
        "y",  # Coordinate
        "z",  # Coordinate
        "e",  # Exception in except blocks
        "_",  # Unused variable
    }
)

# Magic numbers that are commonly acceptable
ALLOWED_MAGIC_NUMBERS = frozenset(
    {
        0,
        1,
        2,
        -1,
        10,
        100,
        1000,
        # Common mathematical constants
        0.0,
        1.0,
        0.5,
        2.0,
        # HTTP status codes pattern matching
        200,
        201,
        204,
        400,
        401,
        403,
        404,
        500,
    }
)
