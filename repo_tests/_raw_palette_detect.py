# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Detector for raw Tailwind palette classes in `.vue` markup (#14580).

`stylelint`'s `color-no-hex` reads `<style>` blocks only. A class written
straight into a template -- `bg-red-50`, `text-gray-700`, `dark:border-blue-500/30`
-- bypasses the design tokens entirely, so a light-red banner stays light-red in
a dark theme and the SLM control plane (6,214 of them) cannot follow a theme at
all.

What counts: a utility prefix (`bg`, `text`, `border`, `ring`, `from`/`via`/`to`,
`divide`, `fill`, `stroke`, `outline`, `decoration`, `accent`, `caret`,
`placeholder`, `shadow`) + a Tailwind palette family + a step (50, 100..900, 950),
optionally `/opacity`, anywhere in a `.vue` file outside its `<style>` blocks.
A variant prefix (`hover:`, `dark:`, `md:`) does not hide it.

What does not: `bg-white`/`text-black` (no step), the design-system utilities
(`bg-autobot-bg-card`), and `@apply` lines inside `<style>`, which `<style>`
scanning owns.

Keyed by the class literal, not the file, for the reason `_hardcoded_colour_detect`
gives: the repetition is the defect, and a per-file pin would list frontend
paths in `repo_tests`. The control plane's keys carry ``SLM_KEY_PREFIX`` so the
two apps keep separate counts.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._hardcoded_colour_detect import REACH_IMPORTANT_FILES, _important_scanned_files

_FRONTEND = Path("autobot-frontend/src")
_SLM_FRONTEND = Path("autobot-slm-frontend/src")
SLM_KEY_PREFIX = "slm:"

_PALETTES = (
    "slate|gray|grey|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|"
    "teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|blueGray"
)
_PREFIXES = (
    "bg|text|border|border-[trblxy]|ring|ring-offset|from|via|to|divide|fill|stroke|"
    "outline|decoration|accent|caret|placeholder|shadow"
)
RAW_PALETTE_CLASS = re.compile(rf"(?<![\w-])(?:{_PREFIXES})-(?:{_PALETTES})-(?:50|[1-9]00|950)(?:/\d{{1,3}})?(?![\w-])")
_STYLE_BLOCK = re.compile(r"<style\b[^>]*>.*?</style>", re.DOTALL | re.IGNORECASE)


#: The population is every `.vue` in both apps -- exactly what the `!important` sweep
#: (#17567) opens -- so this ratchet shares that ONE reach declaration (floor, growth and
#: verdicts live with it) instead of declaring a second for the same files.
REACH_PALETTE_FILES = REACH_IMPORTANT_FILES
scanned_files = _important_scanned_files


def scan_tree(base: Path, prefix: str = "") -> dict[str, int]:
    """``class literal -> count`` over one app's `.vue` files, `<style>` excluded."""
    counts: dict[str, int] = {}
    for path in sorted(base.rglob("*.vue")):
        if "node_modules" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for hit in RAW_PALETTE_CLASS.findall(_STYLE_BLOCK.sub("", text)):
            key = prefix + hit
            counts[key] = counts.get(key, 0) + 1
    return counts


def scan(repo: Path) -> dict[str, int]:
    """The sweep over both apps."""
    counts = scan_tree(repo / _FRONTEND)
    slm = repo / _SLM_FRONTEND
    if slm.is_dir():
        counts.update(scan_tree(slm, SLM_KEY_PREFIX))
    return counts
