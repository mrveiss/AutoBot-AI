# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A colour written in JavaScript cannot follow the theme (#17560).

`[data-theme]` swaps CSS custom properties. A hex literal in a `.ts` or a
component `<script>` is fixed at author time, so every one of them is a
constant colour on a surface that is not -- #17552's defect arriving through
JavaScript instead of through CSS.

The fix is not to delete the colour but to resolve it:
`getCssVar('--color-error', '#ef4444')` reads the theme and keeps the literal
only for the case where no document exists. This ratchet therefore counts that
form as **correct**; a guard that flagged it would penalise its own remedy.

**Two measurement errors this detector exists to not repeat**, both made while
censusing the population and both reported before being caught:

1. `#[0-9a-fA-F]{3,8}` matches `#17552`. Counting issue references as colours
   turned 395 into 6555 and put `router/index.ts` at the top of the table.
2. Counting only `var(--` as a token reference scored `useCssVars.ts` -- the
   file that *defines* the accessor -- at zero tokens, and named the exemplar
   as the worst offender.

Both were arithmetic, correctly executed, answering a different question than
the one they were quoted for.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest
from repo_tests._hardcoded_colour_baseline import (
    EXEMPT_BASENAMES,
    HARDCODED_COLOUR_LITERALS,
    TOTAL_OCCURRENCES,
)
from repo_tests._paths import repo_root

_FRONTEND = Path("autobot-frontend/src")
_SUFFIXES = {".ts", ".vue", ".js"}

#: Theme definitions and generated code are not authored colour decisions.
_SKIP_FRAGMENTS = (
    "assets/css/",
    "assets/tokens.css",
    "assets/tailwind.css",
    "design-tokens/",
    "design-system/",
    "types/generated/",
)

#: CSS hex colours are 3, 4, 6 or 8 digits. Nothing else is one.
_HEX = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})\b")

#: Only lines talking about colour. Precision over recall: a missed literal
#: costs one unratcheted line, a false positive costs someone an argument.
_CONTEXT = re.compile(
    r"colou?r|background|fill|stroke|border|shadow|palette|theme|rgb|gradient|swatch|hsl",
    re.IGNORECASE,
)

#: `<style>` blocks are stylelint's territory -- `color-no-hex` with
#: `postcss-html` already fails on a hex there, and its rule deliberately flags
#: `var(--token, #fallback)` too. Scanning them here would put two guards over
#: one population with different verdicts. This one owns script and template.
_STYLE_BLOCK = re.compile(r"<style\b[^>]*>.*?</style>", re.DOTALL | re.IGNORECASE)

#: The correct forms. In both the hex is a fallback for "the token did not
#: resolve", not a colour decision. TWO spellings, because there are two: the
#: JS accessor `getCssVar('--t', '#hex')`, and CSS `var(--t, #hex)` written
#: inside a JS string -- charts and canvas code use the latter heavily. Matching
#: only the first is the mistake that made this census over-report three times:
#: once counting issue refs as colours, once scoring `useCssVars.ts` at zero
#: tokens, and once reading `var(--border-default, #2d3748)` as a raw literal.
_RESOLVED = re.compile(
    r"getCssVar\s*\(\s*['\"]--[^'\"]+['\"]\s*,\s*['\"](#[0-9a-fA-F]{3,8})['\"]"
    r"|var\(\s*--[A-Za-z0-9_-]+\s*,\s*(#[0-9a-fA-F]{3,8})\s*\)"
)


def _is_colour(token: str) -> bool:
    """Whether *token* is a colour rather than an issue reference.

    `#17552` and `#9909` are issue numbers. A colour either carries a letter
    `a-f` or has a digit count (6 or 8) no issue number in this repo uses.
    """
    digits = token[1:]
    return bool(re.search("[a-fA-F]", digits)) or len(digits) in (6, 8)


def _scan(root: Path) -> dict[str, int]:
    """``lowercased literal -> count`` of colours written instead of resolved.

    Keyed by the literal rather than the file: the repetition is the defect,
    and a per-file result would put frontend paths into this module, which
    changes what CI runs on a frontend edit. See the baseline's docstring.
    """
    counts: dict[str, int] = {}
    for path in sorted(root.rglob("*")):
        if path.suffix not in _SUFFIXES or "node_modules" in path.parts:
            continue
        relative = path.relative_to(root).as_posix()
        if any(fragment in relative for fragment in _SKIP_FRAGMENTS):
            continue
        if path.name in EXEMPT_BASENAMES:
            continue
        if "__tests__" in path.parts or path.name.endswith((".spec.ts", ".test.ts", ".stories.ts")):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if path.suffix == ".vue":
            # Blank the style block, preserving line count so nothing shifts.
            text = _STYLE_BLOCK.sub(lambda m: "\n" * m.group(0).count("\n"), text)
        lines = text.splitlines()
        fallbacks = Counter((a or b).lower() for a, b in _RESOLVED.findall("\n".join(lines)))
        written = Counter(
            match.group(0).lower()
            for line in lines
            for match in _HEX.finditer(line)
            if _is_colour(match.group(0)) and _CONTEXT.search(line)
        )
        for literal, seen in written.items():
            bare = seen - fallbacks.get(literal, 0)
            if bare > 0:
                counts[literal] = counts.get(literal, 0) + bare
    return counts


@pytest.fixture(scope="module")
def measured() -> dict[str, int]:
    root = repo_root() / _FRONTEND
    assert root.is_dir(), f"{_FRONTEND} has moved; this guard reads it by path"
    return _scan(root)


class TestTheDetectorWorksBeforeItsOutputIsRead:
    """Synthetic, so these keep testing something once the baseline drains."""

    def _w(self, tmp_path: Path, name: str, body: str) -> Path:
        (tmp_path / name).write_text(body, encoding="utf-8")
        return tmp_path

    def test_it_finds_a_bare_literal(self, tmp_path):
        self._w(tmp_path, "a.ts", "const c = { color: '#ef4444' }")
        assert _scan(tmp_path) == {"#ef4444": 1}

    def test_an_issue_reference_is_not_a_colour(self, tmp_path):
        # The error that turned 395 into 6555.
        self._w(tmp_path, "a.ts", "// background work for #17552 and #9909 — see the color notes")
        assert _scan(tmp_path) == {}

    def test_a_getcssvar_fallback_is_not_a_finding(self, tmp_path):
        # The error that named the exemplar as the worst offender.
        self._w(tmp_path, "a.ts", "const c = getCssVar('--color-error', '#ef4444')")
        assert _scan(tmp_path) == {}

    def test_a_literal_beside_a_resolved_one_is_still_found(self, tmp_path):
        self._w(
            tmp_path,
            "a.ts",
            "const ok = getCssVar('--color-error', '#ef4444')\nconst bad = { borderColor: '#f59e0b' }\n",
        )
        assert _scan(tmp_path) == {"#f59e0b": 1}

    def test_a_hex_with_no_colour_context_is_ignored(self, tmp_path):
        self._w(tmp_path, "a.ts", "const commit = 'abc123' // see a1b2c3d\nconst id = '#ff00aa'\n")
        assert _scan(tmp_path) == {}

    def test_three_and_eight_digit_colours_count(self, tmp_path):
        self._w(tmp_path, "a.ts", "const a = { color: '#fff' }\nconst b = { background: '#ff00aa80' }\n")
        assert _scan(tmp_path) == {"#fff": 1, "#ff00aa80": 1}

    def test_theme_definitions_are_out_of_scope(self, tmp_path):
        (tmp_path / "assets").mkdir()
        (tmp_path / "assets" / "css").mkdir()
        (tmp_path / "assets" / "css" / "x.ts").write_text("const c = { color: '#ef4444' }", encoding="utf-8")
        assert _scan(tmp_path) == {}

    def test_an_unreadable_file_costs_a_finding_not_the_run(self, tmp_path):
        (tmp_path / "b.ts").write_bytes(b"\xff\xfe color: #ef4444")
        _scan(tmp_path)  # must not raise


class TestTheBaselineIsInternallyConsistent:
    def test_the_total_matches_the_entries(self):
        assert TOTAL_OCCURRENCES == sum(HARDCODED_COLOUR_LITERALS.values())

    def test_no_entry_is_zero(self):
        assert [f for f, n in HARDCODED_COLOUR_LITERALS.items() if n <= 0] == []

    def test_every_entry_is_a_colour_literal(self):
        malformed = [k for k in HARDCODED_COLOUR_LITERALS if not _HEX.fullmatch(k) or not _is_colour(k)]
        assert not malformed, f"baseline keys must be colour literals: {malformed}"

    def test_every_entry_is_lowercased(self):
        # Case-folded, so #FFF and #fff are one entry rather than two.
        assert [k for k in HARDCODED_COLOUR_LITERALS if k != k.lower()] == []

    def test_each_exempt_basename_is_unique_in_the_tree(self):
        root = repo_root() / _FRONTEND
        for name in EXEMPT_BASENAMES:
            found = list(root.rglob(name))
            assert len(found) == 1, f"{name} matches {len(found)} files; a basename exemption needs exactly one"


class TestThePopulationOnlyShrinks:
    def test_no_colour_is_written_more_often(self, measured):
        grew = {
            f: (HARDCODED_COLOUR_LITERALS.get(f, 0), n)
            for f, n in measured.items()
            if n > HARDCODED_COLOUR_LITERALS.get(f, 0)
        }
        assert not grew, (
            f"these colours are written more often than pinned (pinned, now): {grew}. Resolve it from the "
            "theme -- getCssVar('--color-error', '#ef4444') -- so it follows [data-theme]."
        )

    def test_no_new_colour_literal_appears(self, measured):
        new = sorted(set(measured) - set(HARDCODED_COLOUR_LITERALS))
        assert not new, f"these colours are written but never resolved from a token: {new}"

    def test_the_total_never_rises(self, measured):
        assert sum(measured.values()) <= TOTAL_OCCURRENCES

    def test_a_tokenised_colour_is_removed_from_the_baseline(self, measured):
        stale = sorted(f for f in HARDCODED_COLOUR_LITERALS if f not in measured)
        assert (
            not stale
        ), f"these colours are fully tokenised now -- delete their entries and lower TOTAL_OCCURRENCES: {stale}"


class TestTheSharedNotificationSourceStaysShared:
    """#17560's own migration, asserted rather than trusted to the count."""

    def test_cache_management_resolves_its_colours(self):
        source = (repo_root() / "autobot-frontend/src/utils/cacheManagement.ts").read_text(encoding="utf-8")
        assert "getNotificationColors" in source, (
            "cacheManagement.ts stopped using the shared notification colours; it previously "
            "held three disagreeing severity maps"
        )

    def test_it_holds_no_severity_palette_of_its_own(self):
        source = (repo_root() / "autobot-frontend/src/utils/cacheManagement.ts").read_text(encoding="utf-8")
        for gone in ("#2196f3", "#ff9800", "#f44336", "#e3f2fd"):
            assert gone not in source, f"a Material-palette literal is back: {gone}"

    def test_the_shared_source_resolves_rather_than_restates(self):
        source = (repo_root() / "autobot-frontend/src/composables/useCssVars.ts").read_text(encoding="utf-8")
        assert "getNotificationColors" in source
        # Every literal in the mapping must be a getCssVar fallback, never a direct return.
        assert "return '#" not in source, "the shared source returns a literal instead of resolving one"
