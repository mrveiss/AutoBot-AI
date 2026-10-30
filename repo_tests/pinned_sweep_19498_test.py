# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The pinned-file masking helper has one definition, and its mask is the caller's choice (#19498)."""

from __future__ import annotations

import re

import pytest
from repo_tests._paths import repo_root
from repo_tests._pinned_sweep import masked
from repo_tests.service_port_homes_test import read_sources

_MAX_UNREADABLE_MESSAGE = 300


def test_only_the_capture_is_masked_and_the_line_keeps_its_length() -> None:
    text = "A = 8100\nB = 8100\n"
    assert masked(text, r"^A = (\d+)$") == "A = ____\nB = 8100\n"


def test_a_definition_inside_a_multi_line_pin_is_still_swept() -> None:
    text = "a: {{ port | default(8100) }}\nport: 8100\n"
    assert masked(text, r"default\((\d+)\) \}\}\nport") == "a: {{ port | default(____) }}\nport: 8100\n"


def test_the_mask_is_a_parameter() -> None:
    assert masked("A = 8100\n", r"^A = (\d+)$", mask=" ") == "A =     \n"


def test_an_unmatched_optional_group_leaves_the_match_alone() -> None:
    assert masked("A = 1\n", r"^A = (\d+)(x)?$") == "A = _\n"


def test_masked_has_one_definition() -> None:
    """A copy of the helper in any repo_tests module fails here; the home is the one exception."""
    root = repo_root()
    found = [
        path.relative_to(root).as_posix()
        for path in sorted((root / "repo_tests").glob("*.py"))
        if re.search(r"^def masked\(", path.read_text(encoding="utf-8"), re.MULTILINE)
    ]
    assert found == ["repo_tests/_pinned_sweep.py"]


def test_the_unreadable_file_message_stays_short(tmp_path) -> None:
    """The decode error's repr carries the whole byte string; the message must not."""
    (tmp_path / "big.sh").write_bytes(b"\xff" * 45_000)
    with pytest.raises(AssertionError, match=r"big.sh: discovered but unreadable \(not UTF-8 at byte 0") as caught:
        read_sources(tmp_path, ["big.sh"])
    assert len(str(caught.value)) < _MAX_UNREADABLE_MESSAGE
