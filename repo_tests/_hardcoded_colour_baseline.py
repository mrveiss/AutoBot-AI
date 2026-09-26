# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Colour literals the frontend writes instead of resolving (#17560).

**The boundary.** An entry is a hex colour, mapped to how many times it is
written in `autobot-frontend/src` in a `.ts`, `.vue` or `.js` file where:

* it is a real colour -- `#` plus 3, 4, 6 or 8 hex digits, and either carrying
  a letter `a-f` or of a length no issue number in this repo uses. `#17552` in
  a comment is an issue reference, and counting those is how the first census
  of this reported 6555 where the truth was 330;
* it sits on a line mentioning colour, background, fill, stroke, border,
  shadow, gradient, palette or theme -- precision over recall, deliberately;
* it is **not** the fallback of `getCssVar('--token', '#hex')`. That form
  resolves the theme and falls back only when no document exists; it is the
  pattern this ratchet moves code towards, and counting it would penalise the
  remedy.

A literal cannot follow `[data-theme]`, so each one is a fixed colour on a
surface that is not -- #17552's defect arriving through JavaScript.

**Keyed by the literal, not by the file, for three reasons.** The repetition is
the defect: `#fff` written 34 times and `#6b7280` 32 times is one decision
duplicated, and a per-file pin reports that as 34 unrelated problems. Driving
one entry to zero is a complete, checkable piece of work -- that colour is now
tokenised everywhere. And a per-file pin lists frontend paths as literals in a
`repo_tests` module, which `python_filter_covers_its_guards_test.py` reads as a
dependency and would then require the python suite to run on every frontend
edit -- a trade `python_filter_uncovered_reads.py` explicitly refuses.

**Exempt by filename, for a reason** -- these hold literal palettes because the
palette IS their subject:

* `ThemePresetPicker.vue` -- defines the theme presets
* `ComponentShowcaseView.vue` -- a swatch demo

Named by basename rather than path for the same reason as above; both are
unique in the tree, asserted by the guard.

Theme definitions (`assets/css/`, `design-tokens/`, `design-system/`),
generated types, tests and stories are outside the scan entirely.

**Shrink-only.** A count may fall or a literal vanish. Neither may grow, and no
new literal may appear. Replace it with `getCssVar('--token', '#literal')` or a
CSS token -- do not delete a colour to get under the check.
"""

from __future__ import annotations

#: Files whose literal palette is their subject, not a defect. Basenames.
EXEMPT_BASENAMES: frozenset[str] = frozenset({"ThemePresetPicker.vue", "ComponentShowcaseView.vue"})

#: ``lowercased hex literal -> times written instead of resolved``.
HARDCODED_COLOUR_LITERALS: dict[str, int] = {
    "#000000": 1,
    "#007bff": 1,
    "#10b981": 2,
    "#1a1b26": 1,
    "#1e1e1e": 1,
    "#1f2937": 1,
    "#264f78": 1,
    "#313244": 1,
    "#3b82f6": 4,
    "#6366f1": 2,
    "#667eea": 1,
    "#6b7280": 3,
    "#6c757d": 2,
    "#764ba2": 1,
    "#7c3aed": 1,
    "#7f8c8d": 2,
    "#856404": 1,
    "#8b5cf6": 1,
    "#b91c1c": 1,
    "#e5e7eb": 1,
    "#ef4444": 1,
    "#f59e0b": 2,
    "#fecaca": 1,
    "#fef2f2": 1,
    "#ffeaa7": 1,
    "#fff": 5,
    "#fff3cd": 1,
    "#ffffff": 4,
}

#: Frozen total, asserted separately so a per-literal edit cannot drift it unseen.
TOTAL_OCCURRENCES = 45
