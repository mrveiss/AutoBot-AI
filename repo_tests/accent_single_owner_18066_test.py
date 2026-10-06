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

_FRONTEND = repo_root() / "autobot-frontend" / "src"
_SRC_GLOBS = ("**/*.ts", "**/*.vue", "**/*.css")

#: The retired attribute. `accents.css` keys on `data-accent`.
_RETIRED_ATTR = "data-accent-color"

#: A declaration of the accent type. Exactly one module may own it; every other
#: module re-exports or imports that one.
_TYPE_DECL = re.compile(r"^\s*export type AccentColor\s*=\s*'", re.MULTILINE)

#: Anything that writes an accent attribute onto an element.
_SET_ATTR = re.compile(r"""setAttribute\(\s*['"]data-accent[a-z-]*['"]""")


def _sources():
    for pattern in _SRC_GLOBS:
        for path in sorted(_FRONTEND.glob(pattern)):
            if "node_modules" in path.parts:
                continue
            yield path, path.read_text(encoding="utf-8", errors="replace")


def test_the_retired_accent_attribute_is_not_written_or_styled():
    """`data-accent-color` may survive only in prose explaining why it is gone."""
    offenders = []
    for path, text in _sources():
        for lineno, line in enumerate(text.splitlines(), 1):
            if _RETIRED_ATTR not in line:
                continue
            stripped = line.strip()
            # A comment recording the decision is fine; a selector or a write is not.
            if stripped.startswith(("*", "//", "/*", "#")):
                continue
            offenders.append(f"{path.relative_to(_FRONTEND)}:{lineno}: {stripped[:90]}")
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
    assert not _SET_ATTR.search("root.setAttribute('data-theme', mode)")
