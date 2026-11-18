# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20761: one constant-time comparison that never raises on non-ASCII input."""

import hmac
import secrets
from unittest.mock import patch

import pytest

from autobot_shared.security import constant_time
from autobot_shared.security.constant_time import secure_compare

_KEY = "k" * 32  # pragma: allowlist secret


def test_equal_ascii_matches() -> None:
    assert secure_compare(_KEY, _KEY) is True


def test_equal_non_ascii_matches() -> None:
    assert secure_compare("clé-é", "clé-é") is True


def test_ascii_mismatch_is_false() -> None:
    assert secure_compare("a" * 32, "b" * 32) is False


def test_different_length_is_false() -> None:
    assert secure_compare(_KEY, _KEY + "x") is False


@pytest.mark.parametrize("presented", ["é" * 32, "\udcff", "日本語"])
def test_non_ascii_never_raises(presented: str) -> None:
    assert secure_compare(presented, _KEY) is False
    assert secure_compare(_KEY, presented) is False


@pytest.mark.parametrize("a,b", [(None, _KEY), (_KEY, None), (None, None), ("", ""), ("", _KEY), (_KEY, "")])
def test_missing_or_empty_is_false(a, b) -> None:
    assert secure_compare(a, b) is False


def test_bytes_and_str_agree() -> None:
    assert secure_compare(b"abc", "abc") is True
    assert secure_compare(123, "123") is False  # type: ignore[arg-type]


def test_control_str_compare_digest_raises_on_non_ascii() -> None:
    """The defect: the old str call raises, which was the 500."""
    with pytest.raises(TypeError):
        secrets.compare_digest("é" * 32, _KEY)
    with pytest.raises(TypeError):
        hmac.compare_digest("é" * 32, _KEY)


def test_comparison_is_delegated_to_compare_digest() -> None:
    with patch.object(constant_time.hmac, "compare_digest", return_value=True) as digest:
        assert secure_compare("a", "b") is True
    digest.assert_called_once_with(b"a", b"b")
