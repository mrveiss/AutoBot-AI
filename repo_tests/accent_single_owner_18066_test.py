# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The accent colour has exactly one owner, one attribute, one type (#18066).

The accent was implemented twice. `useTheme.applyAccentColor` set
`data-accent`, read by `assets/css/themes/accents.css`; `usePreferences.
applyAccentColor` -- same function name, different module -- set
`data-accent-color`, read by `assets/styles/theme.css`. Both stylesheets were
imported by `main.ts`, so both systems were live and whichever composable ran
last decided the result. The two also declared a type called `AccentColor`
with *different* value sets (8 vs 5), and two different panels imported one
each, so the two accent pickers in the UI offered different colours and wrote
to different attributes.

Nothing errored. A component styled for one attribute while the other was set
simply fell through to base `:root`, which is why the symptom was "the styling
looks non-unified" rather than a failure.

These assertions pin the consolidated state. They are deliberately about the
*shape* -- one writer, one attribute, one declaration -- rather than about the
colour values, which are a design decision and may change.
"""

from __future__ import annotations

import re

from repo_tests._paths import repo_root

from tools.lint._comment_syntax import code_lines, strip_block_comments

_FRONTEND = repo_root() / "autobot-frontend" / "src"
_SRC_GLOBS = ("**/*.ts", "**/*.vue", "**/*.css")

#: The retired attribute. `accents.css` keys on `data-accent`.
_RETIRED_ATTR = "data-accent-color"

#: A declaration of the accent type. Exactly one module may own it; every other
#: module re-exports or imports that one.
_TYPE_DECL = re.compile(r"^\s*export type AccentColor\s*=\s*'", re.MULTILINE)

#: Anything that writes an accent attribute onto an element. Deliberately wider
#: than `data-accent*`: a rival writer is just as much a fork when it is spelled
#: `data-preference-accent` or `data-theme-accent`, and the first version of
#: this guard only matched the prefix it happened to have seen.
_SET_ATTR = re.compile(r"""setAttribute\(\s*['"]data-[a-z-]*accent[a-z-]*['"]""")

#: A base design-token block. These belong in the canonical token file; a second
#: `:root { --color-primary: ... }` elsewhere silently competes with it.
_ROOT_TOKEN_BLOCK = re.compile(r"^:root\s*\{[^}]*--color-primary\s*:", re.MULTILINE)

#: Where base tokens are allowed to live.
_CANONICAL_TOKEN_FILES = {"design-tokens.css"}


def _sources():
    for pattern in _SRC_GLOBS:
        for path in sorted(_FRONTEND.glob(pattern)):
            if "node_modules" in path.parts:
                continue
            yield path, path.read_text(encoding="utf-8", errors="replace")


def test_the_retired_accent_attribute_is_not_written_or_styled():
    """`data-accent-color` may survive only in prose explaining why it is gone."""
    offenders = []
    for path, _text in _sources():
        # #17941: one comment stripper. Testing a line against `//`, `/*`, `#`
        # by hand is a second implementation of comment syntax -- which is the
        # defect this whole PR is about, committed in the guard against it.
        # `strip_block_comments` first: `code_lines` alone does not treat the
        # ` * ...` continuation lines of a `/* */` run as comment, and the
        # decision notes left in theme.css are written exactly that way. It
        # preserves newlines, so line numbers still point at the real file.
        for entry in code_lines(strip_block_comments(_text), name=path):
            if _RETIRED_ATTR not in entry.text:
                continue
            offenders.append(f"{path.relative_to(_FRONTEND)}:{entry.lineno}: {entry.text.strip()[:90]}")
    assert not offenders, (
        "`data-accent-color` is retired (#18066) -- `accents.css` keys on `data-accent`.\n"
        "A second attribute for one concept is the fork this guard exists to stop:\n  " + "\n  ".join(offenders)
    )


def test_exactly_one_module_declares_the_accent_type():
    """Two `AccentColor` declarations with different value sets is the fork."""
    declaring = [str(path.relative_to(_FRONTEND)) for path, text in _sources() if _TYPE_DECL.search(text)]
    assert declaring, "no AccentColor declaration found -- re-derive, do not pass vacuously"
    assert len(declaring) == 1, (
        "AccentColor must be declared once and re-exported elsewhere (#18066). "
        f"Declared in {len(declaring)}: {declaring}"
    )


def test_exactly_one_place_writes_an_accent_attribute():
    """One writer. Delegation is fine; a second `setAttribute` is not."""
    writers = []
    for path, text in _sources():
        for lineno, line in enumerate(text.splitlines(), 1):
            if _SET_ATTR.search(line):
                writers.append(f"{path.relative_to(_FRONTEND)}:{lineno}")
    assert writers, "no accent writer found -- the matcher is broken, not the tree"
    assert len(writers) == 1, (
        "exactly one module may write the accent attribute (#18066); others delegate to it. "
        f"Found {len(writers)}: {writers}"
    )


def test_the_matcher_would_catch_a_regression():
    """Contrast pair: the patterns must fire on the shape they are meant to catch.

    Without this, all three assertions above pass just as happily against a
    broken matcher as against a clean tree.
    """
    assert _TYPE_DECL.search("export type AccentColor = 'blue' | 'red'")
    assert not _TYPE_DECL.search("export type AccentColor = ThemeAccentColor")
    assert _SET_ATTR.search("root.setAttribute('data-accent-color', color)")
    assert _SET_ATTR.search('el.setAttribute("data-accent", accent)')
    # A rival spelling is still a rival writer.
    assert _SET_ATTR.search("root.setAttribute('data-preference-accent', c)")
    assert not _SET_ATTR.search("root.setAttribute('data-theme', mode)")
    assert not _SET_ATTR.search("root.setAttribute('data-font-size', size)")
    assert _ROOT_TOKEN_BLOCK.search(":root {\n  --color-primary: #ff00ff;\n}")
    assert not _ROOT_TOKEN_BLOCK.search('[data-accent="teal"] {\n  --color-primary: #14b8a6;\n}')


def test_base_tokens_live_only_in_the_canonical_file():
    """A second `:root` defining --color-primary competes with the token source.

    Accent *variants* are keyed on `[data-accent=...]` and may live in
    accents.css; a bare `:root` block redefining the base token is a second
    declaration of the default, which is the same fork one level down.
    """
    offenders = []
    for path, text in _sources():
        if path.name in _CANONICAL_TOKEN_FILES:
            continue
        if _ROOT_TOKEN_BLOCK.search(strip_block_comments(text)):
            offenders.append(str(path.relative_to(_FRONTEND)))
    assert not offenders, (
        "base design tokens are declared once, in "
        f"{sorted(_CANONICAL_TOKEN_FILES)} (#18066). A `:root` block redefining "
        "--color-primary elsewhere competes with it:\n  " + "\n  ".join(offenders)
    )
