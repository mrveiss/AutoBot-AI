# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Regression tests for get_trust_manager() lazy_singleton pattern (MVA-1359 / GH#8741).

Verifies that get_trust_manager() returns a TrustScoreManager instance (not a
callable) and that repeated calls return the same object.
"""

import inspect
from unittest.mock import patch

from a2a.trust_score import TrustScoreManager, get_trust_manager


def test_get_trust_manager_returns_instance_not_callable():
    """get_trust_manager() must return a TrustScoreManager, not a function."""
    with patch.object(TrustScoreManager, "__init__", return_value=None):
        result = get_trust_manager()
    assert not inspect.isfunction(result), (
        f"get_trust_manager() returned {type(result).__name__!r}; "
        "expected TrustScoreManager instance — bare module-level global regression"
    )
    assert isinstance(result, TrustScoreManager)


def test_get_trust_manager_is_singleton():
    """Two calls to get_trust_manager() must return the same object."""
    with patch.object(TrustScoreManager, "__init__", return_value=None):
        a = get_trust_manager()
        b = get_trust_manager()
    assert a is b, "get_trust_manager() must return the same singleton instance on every call"
