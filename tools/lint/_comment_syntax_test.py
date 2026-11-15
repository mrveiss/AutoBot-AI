# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the length-preserving blanking in tools/lint/_comment_syntax.py (#21195).

`blank_comments` and `blank_comments_and_strings` blank at the same length,
so offsets in the masked text still resolve in the original — a caller that
matches a literal or walks braces must see the code where it actually is.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

_PATH = Path(__file__).parent / "_comment_syntax.py"
_spec = importlib.util.spec_from_file_location("_comment_syntax_under_test", _PATH)
assert _spec is not None and _spec.loader is not None
shared = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(shared)


def test_blank_comments_blanks_line_and_block_comments_at_equal_length():
    text = "a = 1; // trail\nb = 2; /* block\nstill */ c = 3;\n"
    masked = shared.blank_comments(text)
    assert len(masked) == len(text)
    assert masked.splitlines() == [
        "a = 1; " + " " * len("// trail"),
        "b = 2; " + " " * len("/* block"),
        " " * len("still */") + " c = 3;",
    ]


def test_blank_comments_keeps_string_literals_so_a_literal_still_matches():
    text = "a.setAttribute('download', name); // a.download = x\n"
    masked = shared.blank_comments(text)
    assert "'download'" in masked
    assert "a.download = x" not in masked
    assert len(masked) == len(text)


def test_blank_comments_does_not_read_a_comment_marker_inside_a_string():
    text = 'const u = "http://example.com"; a.download = name\n'
    assert shared.blank_comments(text) == text


def test_blank_comments_does_not_open_a_literal_inside_a_comment():
    text = "// don't\nconst el = document.createElement('a');\n"
    assert shared.blank_comments(text) == " " * len("// don't") + "\nconst el = document.createElement('a');\n"


def test_blank_comments_and_strings_blanks_literals_too():
    text = "const s = 'a{b}'; // c\n"
    masked = shared.blank_comments_and_strings(text)
    assert masked == "const s = " + " " * len("'a{b}'") + ";" + " " * len(" // c") + "\n"
    assert len(masked) == len(text)


def test_single_line_quotes_end_at_the_newline():
    # An apostrophe in .vue template text must not pair with an apostrophe
    # later in the script and blank the code in between (#21195).
    text = "<template><p>Don't</p></template>\nconst el = x; // x.download = 1\nconst note = \"it's\";\n"
    masked = shared.blank_comments(text)
    assert "// x.download = 1" not in masked
    assert "const el = x;" in masked
    assert len(masked) == len(text)
    braced = shared.blank_comments_and_strings(text)
    assert "const el = x;" in braced
    assert "// x.download = 1" not in braced


def test_backtick_templates_may_span_lines():
    text = "const t = `a\nb`; // done\n"
    masked = shared.blank_comments(text)
    assert masked == "const t = `a\nb`;" + " " * len(" // done") + "\n"
    braced = shared.blank_comments_and_strings(text)
    assert braced == "const t = " + " " * len("`a") + "\n" + " " * len("b`") + ";" + " " * len(" // done") + "\n"
