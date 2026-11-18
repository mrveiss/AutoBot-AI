# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one ``.env`` reader keeps a quoted value's text and drops a trailing comment (#19232)."""

import pytest

from autobot_shared.env_file import parse_env_text


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ('KEY="2" # note', "2"),  # quoted, then a comment: the quotes used to survive
        ("KEY='2' #x", "2"),
        ('KEY="a # b"', "a # b"),  # a # inside quotes is data
        ('KEY="2"', "2"),
        ("KEY=2 # note", "2"),  # unquoted: ` #` opens a comment
        ("KEY=a#b", "a#b"),  # no space: not a comment
        ('KEY="2" trailing', '"2" trailing'),  # text after the quote is not a comment: kept verbatim
        ('KEY="unterminated # c', '"unterminated'),  # no closing quote: the unquoted rule applies
        ("KEY=", ""),
    ],
)
def test_value_forms(line: str, expected: str) -> None:
    assert parse_env_text(line) == {"KEY": expected}


def test_comment_and_blank_lines_are_skipped() -> None:
    assert parse_env_text("# c\n\nA=1\nB='two' # why\n") == {"A": "1", "B": "two"}
