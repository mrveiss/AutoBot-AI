# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Contrast tests for the canonical ``__main__``-guard detector (#22199)."""

from __future__ import annotations

import pytest

from tools.lint._main_guard import source_has_main_guard


@pytest.mark.parametrize(
    "source,expected",
    [
        ('if __name__ == "__main__":\n    pass\n', True),
        ('if __name__ != "__main__":\n    pass\n', False),
        ('"""\nif __name__ == "__main__":\n"""\n', False),
        ("if __name__ == '__main__'\n    pass\n", False),  # unparsable source has no readable guard
    ],
)
def test_source_has_main_guard(source: str, expected: bool) -> None:
    assert source_has_main_guard(source) is expected
