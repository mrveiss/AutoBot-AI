# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for memory/compat.py singleton accessors (Bug #5622).

get_enhanced_memory_manager() and get_long_term_memory_manager() must return
class instances, not the lazy_singleton callable.
"""

import inspect
from unittest.mock import patch

from memory.compat import (
    EnhancedMemoryManager,
    LongTermMemoryManager,
    get_enhanced_memory_manager,
    get_long_term_memory_manager,
)
from memory.manager import UnifiedMemoryManager


def test_get_enhanced_memory_manager_returns_instance_not_callable():
    """get_enhanced_memory_manager() must return EnhancedMemoryManager, not a function."""
    with patch.object(UnifiedMemoryManager, "__init__", return_value=None):
        result = get_enhanced_memory_manager()
    assert not inspect.isfunction(result), (
        f"get_enhanced_memory_manager() returned {type(result).__name__!r}; " "expected EnhancedMemoryManager instance"
    )
    assert isinstance(result, EnhancedMemoryManager)


def test_get_long_term_memory_manager_returns_instance_not_callable():
    """get_long_term_memory_manager() must return LongTermMemoryManager, not a function."""
    with patch.object(UnifiedMemoryManager, "__init__", return_value=None):
        result = get_long_term_memory_manager()
    assert not inspect.isfunction(result), (
        f"get_long_term_memory_manager() returned {type(result).__name__!r}; " "expected LongTermMemoryManager instance"
    )
    assert isinstance(result, LongTermMemoryManager)


def test_get_enhanced_memory_manager_singleton():
    """Two calls return the same object."""
    with patch.object(UnifiedMemoryManager, "__init__", return_value=None):
        a = get_enhanced_memory_manager()
        b = get_enhanced_memory_manager()
    assert a is b


def test_get_long_term_memory_manager_singleton():
    """Two calls return the same object."""
    with patch.object(UnifiedMemoryManager, "__init__", return_value=None):
        a = get_long_term_memory_manager()
        b = get_long_term_memory_manager()
    assert a is b
