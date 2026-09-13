# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Upload allowlists hold whole extensions, never truncated ones (#16521).

``conversation_files.ALLOWED_EXTENSIONS`` listed ``".pd"`` and ``".gi"`` where
``".pdf"`` and ``".gif"`` were meant. The validator compares a filename's whole
suffix against the set, so no real file ever matched them, and every PDF and
GIF attached to a conversation was refused. ``files.py`` carried the same two
entries beside the correct spellings, where they were dead.

These tests go through the real validators rather than asserting on the set
literals alone, so they fail on the behaviour a user would hit.
"""

import pytest

from api import conversation_files, files

# Real extensions where one spelling is a prefix of another. Any other pair of
# that shape in an allowlist is a truncated entry.
_LEGITIMATE_PREFIX_PAIRS = frozenset(
    {
        (".doc", ".docx"),
        (".js", ".json"),
        (".ppt", ".pptx"),
        (".xls", ".xlsx"),
    }
)


@pytest.mark.parametrize(
    "validator",
    [conversation_files.is_safe_file, files.is_safe_file],
    ids=["conversation_files", "files"],
)
@pytest.mark.parametrize("filename", ["report.pdf", "animation.gif", "REPORT.PDF"])
def test_pdf_and_gif_uploads_are_accepted(validator, filename):
    assert validator(filename) is True


def test_no_allowlist_holds_a_truncated_extension():
    union = conversation_files.ALLOWED_EXTENSIONS | files.ALLOWED_EXTENSIONS
    pairs = {(short, long) for short in union for long in union if short != long and long.startswith(short)}
    assert pairs <= _LEGITIMATE_PREFIX_PAIRS, sorted(pairs - _LEGITIMATE_PREFIX_PAIRS)
