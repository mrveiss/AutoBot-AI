# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Shared type definitions for AutoBot
"""

from enum import Enum


class TaskComplexity(Enum):
    SIMPLE = "simple"  # Regular conversation with Knowledge Base integration
    COMPLEX = "complex"  # Requires tools, research, or system actions

    # RESEARCH, INSTALL, and SECURITY_SCAN were removed (issue #13806).
    # They were aliases of COMPLEX — same value, same object — so a dict
    # keyed on all five members collapsed to two entries with last-write-wins
    # behaviour.  Every call site that used them now uses COMPLEX directly.
    # If a future author needs distinct complexity values, add genuinely
    # distinct enum members here, not same-value aliases.
