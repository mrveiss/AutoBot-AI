#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
check_token_contrast.py — WCAG AA contrast gate for AutoBot design tokens (#12730).

The GUI-consistency umbrella (#12730) lists four enforcement mechanisms that stop
the drift it catalogues from returning. Three already exist (stylelint
``color-no-hex``, the ApiClient/raw-fetch eslint selectors, the deprecated
size/colour token rules). A contrast check was the missing one, and #12711
reported the symptom it would have caught: text rendered dark-on-dark and
light-on-light.

This checks the *token definitions*, not rendered pixels. That is deliberate:
tokens are where a contrast decision is actually made, and checking them needs
no browser, so it can gate every PR cheaply.

Pairs are derived by naming convention rather than hand-listed, so a new
``--text-on-<x>`` token is covered the moment it is added:

    --text-on-<x>  against  --color-<x>          (foreground on a semantic fill)
    --text-<y>     against  --bg-primary         (body text on the app background)

Usage:
    python3 scripts/check_token_contrast.py            # report + non-zero exit on failure
    python3 scripts/check_token_contrast.py --report   # report only, always exit 0
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
TOKENS_CSS = REPO_ROOT / "autobot-frontend" / "src" / "assets" / "css" / "design-tokens.css"

# WCAG 2.1 AA: 4.5:1 for normal text, 3.0:1 for large text and UI components.
AA_NORMAL = 4.5
AA_LARGE = 3.0

# Body-text tokens are read against the app background. --text-inverse is
# excluded by design: it exists precisely to sit on an inverted surface, so
# measuring it against --bg-primary would report a failure that is correct
# behaviour.
_BODY_TEXT_TOKENS = ("--text-primary", "--text-secondary", "--text-tertiary", "--text-muted")
_BODY_BACKGROUND = "--bg-primary"

_HEX_DECL = re.compile(r"^\s*(--[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\s*;", re.MULTILINE)
_ANY_COLOR_DECL = re.compile(
    r"^\s*(--[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8}|rgb[a]?\([^)]*\)|hsl[a]?\([^)]*\)|oklch\([^)]*\))\s*;",
    re.MULTILINE,
)


def parse_hex_tokens(css: str) -> Dict[str, str]:
    """Map token name -> hex value for every hex-valued custom property.

    Only the first definition of a name is kept: later ones are theme overrides
    (``oklch`` wide-gamut blocks, media queries), which are reported as skipped
    rather than silently folded in.
    """
    tokens: Dict[str, str] = {}
    for name, value in _HEX_DECL.findall(css):
        tokens.setdefault(name, value.lower())
    return tokens


def parse_non_hex_tokens(css: str) -> Dict[str, str]:
    """Colour tokens defined in a format this checker cannot evaluate."""
    skipped: Dict[str, str] = {}
    hex_names = set(parse_hex_tokens(css))
    for name, value in _ANY_COLOR_DECL.findall(css):
        if name not in hex_names:
            skipped.setdefault(name, value.strip())
    return skipped


def _to_rgb(hex_value: str) -> Tuple[int, int, int]:
    """Parse #rgb / #rrggbb / #rrggbbaa into an (r, g, b) triple."""
    h = hex_value.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def relative_luminance(hex_value: str) -> float:
    """WCAG 2.1 relative luminance of a colour."""
    channels = []
    for raw in _to_rgb(hex_value):
        c = raw / 255.0
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    """WCAG contrast ratio between two colours (1.0 – 21.0)."""
    l1, l2 = relative_luminance(fg_hex), relative_luminance(bg_hex)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def build_pairs(tokens: Dict[str, str]) -> List[Tuple[str, str, float]]:
    """Derive (foreground, background, required_ratio) pairs by convention."""
    pairs: List[Tuple[str, str, float]] = []

    for name in sorted(tokens):
        if not name.startswith("--text-on-"):
            continue
        semantic = name[len("--text-on-") :]
        background = f"--color-{semantic}"
        if background in tokens:
            # A filled button/badge is a UI component with large-ish label text.
            pairs.append((name, background, AA_LARGE))

    for text_token in _BODY_TEXT_TOKENS:
        if text_token in tokens and _BODY_BACKGROUND in tokens:
            pairs.append((text_token, _BODY_BACKGROUND, AA_NORMAL))

    return pairs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", action="store_true", help="report only; always exit 0")
    ap.add_argument("--css", default=str(TOKENS_CSS), help="token stylesheet to check")
    args = ap.parse_args()

    css_path = Path(args.css)
    if not css_path.is_file():
        print(f"[contrast] token stylesheet not found: {css_path}", file=sys.stderr)
        return 2

    css = css_path.read_text(encoding="utf-8")
    tokens = parse_hex_tokens(css)
    skipped = parse_non_hex_tokens(css)
    pairs = build_pairs(tokens)

    print(f"[contrast] {css_path.relative_to(REPO_ROOT)}")
    print(f"[contrast] {len(tokens)} hex tokens, {len(pairs)} derived pairs, {len(skipped)} non-hex tokens skipped")

    failures = []
    for fg, bg, required in pairs:
        ratio = contrast_ratio(tokens[fg], tokens[bg])
        ok = ratio >= required
        marker = "ok  " if ok else "FAIL"
        print(f"  {marker} {ratio:5.2f}:1 (need {required})  {fg} on {bg}")
        if not ok:
            failures.append((fg, bg, ratio, required))

    if skipped:
        # Never let the gate imply coverage it does not have.
        print(f"[contrast] NOT CHECKED ({len(skipped)} tokens in a non-hex format):")
        for name, value in list(sorted(skipped.items()))[:10]:
            print(f"    {name}: {value}")
        if len(skipped) > 10:
            print(f"    … and {len(skipped) - 10} more")

    if failures:
        print(f"\n[contrast] {len(failures)} pair(s) below WCAG AA:")
        for fg, bg, ratio, required in failures:
            print(f"    {fg} on {bg}: {ratio:.2f}:1 < {required}")
        if not args.report:
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
