# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for memory/compat.py singleton accessors (Bug #5622, updated #10572, #10666).

get_memory_manager() and get_long_term_memory_manager() must return
class instances, not the lazy_singleton callable.

#10572: EnhancedMemoryManager class removed.
#10666 B2: UnifiedMemoryManager renamed to MemoryManager; get_enhanced_memory_manager
removed — canonical factory is get_memory_manager().
"""

import inspect
from unittest.mock import patch

from memory.compat import (
    LongTermMemoryManager,
    get_long_term_memory_manager,
    get_memory_manager,
)
from memory.manager import MemoryManager


def test_get_memory_manager_returns_instance_not_callable():
    """get_memory_manager() must return MemoryManager, not a function."""
    with patch.object(MemoryManager, "__init__", return_value=None):
        result = get_memory_manager()
    assert not inspect.isfunction(
        result
    ), f"get_memory_manager() returned {type(result).__name__!r}; expected MemoryManager instance"
    assert isinstance(result, MemoryManager)


def test_get_long_term_memory_manager_returns_instance_not_callable():
    """get_long_term_memory_manager() must return LongTermMemoryManager, not a function."""
    with patch.object(MemoryManager, "__init__", return_value=None):
        result = get_long_term_memory_manager()
    assert not inspect.isfunction(result), (
        f"get_long_term_memory_manager() returned {type(result).__name__!r}; " "expected LongTermMemoryManager instance"
    )
    assert isinstance(result, LongTermMemoryManager)


def test_get_memory_manager_singleton():
    """Two calls to get_memory_manager() return the same object."""
    with patch.object(MemoryManager, "__init__", return_value=None):
        a = get_memory_manager()
        b = get_memory_manager()
    assert a is b


def test_get_long_term_memory_manager_singleton():
    """Two calls to get_long_term_memory_manager() return the same object."""
    with patch.object(MemoryManager, "__init__", return_value=None):
        a = get_long_term_memory_manager()
        b = get_long_term_memory_manager()
    assert a is b
