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


# AC2 of #16521 asks for more than the prefix-pair check above: *every* entry in
# both allowlists must be a real extension spelling from a named list.
#
# The prefix check only catches a truncation whose full form is ALSO in the set —
# that is how `.pd`/`.pdf` and `.gi`/`.gif` presented. It cannot see a truncation
# standing alone, and one was: `.con` sat in files.py's config cluster
# (`.log`, `.cfg`, `.ini`, `.con`) with no `.conf` anywhere in the set, so no pair
# existed to flag. It had been there since #926, and the consequence was the same
# shape as the PDF bug — `.conf` uploads refused, `.con` accepted.
#
# `mimetypes.types_map` is the named list, plus an explicit set of real extensions
# Python's table simply lacks. That second set is the part that must stay honest:
# every addition needs to be a real spelling, not a convenient way to silence the
# guard, which is why each carries a reason.
_MIMETYPES_GAPS = {
    ".cfg": "config file; not in Python's mimetypes table",
    ".conf": "config file; not in Python's mimetypes table",
    ".ini": "config file; not in Python's mimetypes table",
    ".log": "plain-text log; not in Python's mimetypes table",
    ".yaml": "YAML; absent from mimetypes before Python 3.13",
    ".yml": "YAML; absent from mimetypes before Python 3.13",
}


def _allowlist_entries() -> set[str]:
    """Every extension both modules accept, read from the modules themselves."""
    found: set[str] = set()
    for module in (conversation_files, files):
        for name in dir(module):
            if not name.isupper():
                continue
            value = getattr(module, name)
            if (
                isinstance(value, (set, frozenset))
                and value
                and all(isinstance(v, str) and v.startswith(".") for v in value)
            ):
                found |= {v.lower() for v in value}
    return found


def test_the_entry_scan_still_finds_allowlists():
    """A zero here means the scan drifted, not that the allowlists are empty."""
    assert _allowlist_entries(), "no extension allowlist found in either module — this guard is blind"


def test_every_allowlist_entry_is_a_real_extension():
    """A truncation standing alone has no prefix pair, so only a named list catches it (#16521)."""
    import mimetypes

    mimetypes.init()
    known = {e.lower() for e in mimetypes.types_map} | set(_MIMETYPES_GAPS)
    unknown = sorted(_allowlist_entries() - known)
    assert not unknown, (
        f"allowlist entries that are not real extension spellings: {unknown}. Either the entry is a "
        f"truncation (the #16521 defect) or it is real and belongs in _MIMETYPES_GAPS with a reason."
    )
