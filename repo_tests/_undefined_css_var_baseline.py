# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Custom properties referenced in the frontend but declared nowhere (#17552).

**The boundary.** An entry is a property NAME, mapped to how many times it is
referenced from ``autobot-frontend/src`` in a way that renders nothing:

* the reference supplies **no fallback** -- ``var(--x, #fff)`` is fine, the
  fallback is what renders;
* the name is assigned nowhere in that tree in a ``.css``, ``.scss``, ``.vue``,
  ``.ts`` or ``.js`` file;
* the name is not one Tailwind v4 supplies itself.

Such a reference is not inert. It makes the declaration *invalid at
computed-value time*, so ``background`` renders ``transparent``, ``color``
silently **inherits**, and a ``border`` shorthand is dropped entirely. That is
what produced pale text on pale surfaces across the GUI.

**Keyed by name, not by file, for two reasons.** The name is the unit the rule
is about -- defining ``--terminal-bg`` once fixes all five of its sites, and a
per-file pin would report that as five unrelated improvements. And a per-file
pin would list frontend paths as concrete literals in a ``repo_tests`` module,
which ``python_filter_covers_its_guards_test.py`` reads as "this guard depends
on those files" and would then require the python suite to run on every
frontend edit -- a trade ``python_filter_uncovered_reads.py`` explicitly
refuses for frontend component changes.

**Shrink-only.** A count may fall or a name vanish. Neither may grow, and no
new name may appear. Fix the reference -- do not add a fallback purely to get
under the check, because a fallback hard-codes a colour that then ignores the
theme, which is the same defect wearing a different hat.

Frozen at 134 sites over 72 names, after #17552 cleared the ``--autobot-*``
namespace (46 sites) and six ``--color-``prefixed names (32 sites).
"""

from __future__ import annotations

#: ``property name -> references that render nothing``.
UNDEFINED_CSS_VAR_NAMES: dict[str, int] = {
    "--accent-primary": 1,
    "--bg-backdrop": 2,
    "--bg-button-primary": 1,
    "--bg-button-primary-active": 1,
    "--bg-button-primary-hover": 1,
    "--bg-card-rgb": 2,
    "--bg-hover-alpha-10": 1,
    "--bg-inverse": 2,
    "--border-hover": 3,
    "--color-background-hover": 5,
    "--color-background-secondary": 3,
    "--color-bg": 2,
    "--color-bg-subtle": 3,
    "--color-border-hover": 1,
    "--color-danger-border": 1,
    "--color-error-active": 1,
    "--color-error-bg-transparent": 3,
    "--color-error-darker": 1,
    "--color-error-rgb": 3,
    "--color-error-shadow": 1,
    "--color-error-text": 4,
    "--color-info-active": 1,
    "--color-info-bg-transparent": 1,
    "--color-info-border": 2,
    "--color-primary-alpha-30": 4,
    "--color-primary-bg-transparent": 1,
    "--color-primary-border": 1,
    "--color-primary-rgb": 1,
    "--color-primary-transparent": 2,
    "--color-purple-bg-transparent": 1,
    "--color-success-bg-transparent": 3,
    "--color-success-rgb": 2,
    "--color-surface-hover": 3,
    "--color-warning-active": 1,
    "--color-warning-bg-light": 3,
    "--color-warning-bg-transparent": 2,
    "--color-warning-darker": 3,
    "--errmon-y": 1,
    "--font-size-md": 7,
    "--indigo-800": 1,
    "--ring-primary": 4,
    "--shadow-error": 1,
    "--shadow-success": 1,
    "--status-warning": 3,
    "--terminal-bg": 5,
    "--terminal-bg-dark": 1,
    "--terminal-button-bg": 1,
    "--terminal-button-bg-hover": 1,
    "--terminal-button-border": 1,
    "--terminal-button-text": 1,
    "--terminal-cyan": 3,
    "--terminal-foreground": 2,
    "--terminal-green": 4,
    "--terminal-green-bg": 1,
    "--terminal-green-bg-hover": 1,
    "--terminal-green-border": 1,
    "--terminal-green-border-hover": 1,
    "--terminal-header-bg": 1,
    "--terminal-magenta": 2,
    "--terminal-muted": 1,
    "--terminal-red": 1,
    "--terminal-scrollbar-thumb": 1,
    "--terminal-scrollbar-track": 1,
    "--terminal-yellow": 1,
    "--text-disabled": 5,
    "--text-error": 1,
    "--text-info": 1,
    "--text-on-primary-bg": 1,
    "--text-primary-dark": 1,
    "--text-tertiary-alpha-10": 1,
    "--text-warning": 1,
    "--token-name": 1,
}

#: Frozen total, asserted separately so a per-name edit cannot drift it unseen.
TOTAL_SITES = 134
