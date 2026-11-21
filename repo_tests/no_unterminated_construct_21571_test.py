# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No tracked source file ends inside a block comment or a quote (#21571 AC4).

`tools.lint._comment_syntax.code_lines` does not raise when a file ends inside a construct: about a hundred
guards read through it, so every line after the opener is blanked and each of them goes blind to it without a
sound. `unterminated_construct` reports it; this guard runs it over the tracked tree, so the count of lines
blanked that way on the real tree is pinned at zero rather than measured once.

The population is every tracked non-test file whose suffix has block comments (`BLOCK_COMMENT_SUFFIXES`, the
helper's own set, not a copy). A test file may hold an unterminated sample as data.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared.testfile_names import is_test_filename
from tools.lint._comment_syntax import BLOCK_COMMENT_SUFFIXES, unterminated_construct
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths


def _discover(root: Path) -> list[str]:
    """Tracked non-test files with a block-comment suffix; an empty tree yields [] so the floor refuses."""
    try:
        tracked = tracked_paths(Path(root), ".")
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if Path(rel).suffix in BLOCK_COMMENT_SUFFIXES and not is_test_filename(rel)]


REACH = declare(
    "no-unterminated-construct-21571",
    discover=_discover,
    floor=1834,  # measured on this tree; a new guard pins until it lands on the base (#19676)
    growth=200,
    what="tracked non-test files whose suffix has block comments",
)


def _unterminated(rels: list[str], root: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    for rel in rels:
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        ended = unterminated_construct(text, name=rel)
        if ended is not None:
            found[rel] = ended
    return found


def test_no_tracked_source_file_ends_inside_a_comment_or_a_quote() -> None:
    root = repo_root()
    files = _discover(root)
    REACH.completed(files, root)
    assert _unterminated(files, root) == {}, (
        "#21571: these files end inside a construct, so every line after the opener is blanked for every guard "
        "that reads through `code_lines`; close the comment or the quote"
    )


@pytest.mark.parametrize(
    ("rel", "text", "ended"),
    [
        ("a.ts", "const a = 1 /* never closed\nconst b = 2\n", "block comment"),
        ("b.js", "const a = `never closed\nconst b = 2\n", "quote"),
        ("c.vue", "<script>\n/* never closed\n</script>\n", "block comment"),
    ],
)
def test_contrast_a_planted_unterminated_file_is_flagged(tmp_path: Path, rel: str, text: str, ended: str) -> None:
    """The detector can fire: a synthetic file ending inside a construct is reported, by kind."""
    (tmp_path / rel).write_text(text, encoding="utf-8")
    assert _unterminated([rel], tmp_path) == {rel: ended}


def test_contrast_a_closed_file_is_not_flagged(tmp_path: Path) -> None:
    """...and it stays quiet on a file whose comments and quotes all close, in the same tree."""
    (tmp_path / "ok.ts").write_text("const a = 'x' /* closed */\nconst b = `y`\n", encoding="utf-8")
    (tmp_path / "bad.ts").write_text("const a = 1 /* never closed\n", encoding="utf-8")
    assert _unterminated(["ok.ts", "bad.ts"], tmp_path) == {"bad.ts": "block comment"}
