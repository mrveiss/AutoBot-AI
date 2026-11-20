# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No source file ends the shared comment pass inside a comment, a quote or a hidden template (#21571).

`tools.lint._comment_syntax.code_lines` reads a file once for about a hundred guards. A `/*` in `.vue` template prose
(``/api/errors/*``) opened a block comment that blanked every line to the next ``*/`` or the end of the file, so each
guard was blind in that region and reported nothing for it. The helper now reads a component's template as markup and
`unterminated_construct` names a file whose pass ends inside a block comment or a quote.

**The boundary.** Every tracked `.vue`, `.ts`, `.mts`, `.cts`, `.js`, `.mjs`, `.cjs` and `.json5` file outside
``node_modules`` and outside test files (`is_test_filename`: a test fixture spells `/*` on purpose). Two claims:
the pass ends in code for every one of them, and no line of a `.vue` root template is missing from `code_lines`
(the 132 class-bearing lines the issue measured at ``d142a6a813`` are 0 now). The template check is its own
derivation, a line regex over the root ``<template>`` block, not the helper's region split.

**What it does not claim.** A `.vue` file with no root block is scanned whole, as a snippet; a ``<!-- -->`` comment is
left in the template text by design (`strip_html_comments` removes it), so a guard that wants it gone asks for that.
The reach floor guards the enumeration: a moved folder would otherwise read as a clean pass. No ``roots=`` is declared:
the hand-written scope record (``_reach_declared_scopes``) is held by open PRs, so the guard runs on every push until a
follow-up adds it there.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared.testfile_names import is_test_filename
from tools.lint._comment_syntax import code_lines, unterminated_construct
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_SUFFIXES = ("*.vue", "*.ts", "*.mts", "*.cts", "*.js", "*.mjs", "*.cjs", "*.json5")
_ROOT_TEMPLATE = re.compile(r"^<template\b.*?^</template>", re.DOTALL | re.MULTILINE)


def _sources(root: Path) -> list[str]:
    """The tracked source files the shared pass reads, outside tests; ``[]`` on an empty tree (the floor then fires)."""
    try:
        found = tracked_paths(root, *_SUFFIXES, exclude=("node_modules",))
    except EmptyEnumeration:
        return []
    return [p for p in found if not is_test_filename(p)]


#: 1830 measured at the base (#21571); a new declaration has no base to compute a floor from, so it pins ``floor=``.
REACH = declare(
    "comment-helper-terminates-21571",
    discover=_sources,
    what="frontend source files read by the shared comment helper",
    floor=1770,
    growth=100,
)


def _blanked_template_lines(text: str, shown: set[int]) -> list[int]:
    """Line numbers inside the root template that carry text but are absent from the helper's output."""
    found = _ROOT_TEMPLATE.search(text)
    if found is None:
        return []
    first = text.count("\n", 0, found.start()) + 1
    return [first + i for i, line in enumerate(found.group().splitlines()) if line.strip() and first + i not in shown]


def test_no_source_file_ends_the_pass_inside_a_comment_or_a_quote() -> None:
    root = repo_root()
    ended = {p: unterminated_construct(root / p) for p in REACH.examined(root)}
    assert not {p: kind for p, kind in ended.items() if kind}, "the rest of these files is invisible to every guard"


def test_no_line_of_a_vue_root_template_is_blanked() -> None:
    root = repo_root()
    blanked = {}
    for rel in (p for p in REACH.examined(root) if p.endswith(".vue")):
        shown = {line.lineno for line in code_lines(root / rel)}
        missing = _blanked_template_lines((root / rel).read_text(encoding="utf-8"), shown)
        if missing:
            blanked[rel] = missing[:5]
    assert not blanked, blanked


# --- the detector finds what it is for: known positives, so a clean result above is a measurement ----------------

_BLANKING_TEMPLATE = '<template>\n  <p>Backed by /api/errors/*</p>\n  <div class="seen">x</div>\n</template>\n<script>\n/* ok */\n</script>\n'


def test_the_pass_reports_an_unterminated_block_comment_and_quote() -> None:
    assert unterminated_construct("const a = 1 /* open\nconst b = 2\n", name="x.ts") == "block comment"
    assert unterminated_construct("const a = `open\nconst b = 2\n", name="x.ts") == "quote"
    assert unterminated_construct("const a = 1 /* closed */\n", name="x.ts") is None


def test_the_template_check_sees_a_line_the_helper_would_blank() -> None:
    assert _blanked_template_lines(_BLANKING_TEMPLATE, set()) == [1, 2, 3, 4]
    shown = {line.lineno for line in code_lines(_BLANKING_TEMPLATE, name="x.vue")}
    assert _blanked_template_lines(_BLANKING_TEMPLATE, shown) == [], "the helper blanks a template line"


@pytest.mark.parametrize("name", ["x.vue", "x.ts"])
def test_a_planted_file_ending_in_a_block_comment_is_flagged(name: str, tmp_path: Path) -> None:
    source = "<script>\n/* never closed\n</script>\n" if name.endswith(".vue") else "/* never closed\nconst a = 1\n"
    planted = tmp_path / name
    planted.write_text(source, encoding="utf-8")
    assert unterminated_construct(planted) == "block comment"
