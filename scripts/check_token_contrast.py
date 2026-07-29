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
import math
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

    Only the first definition of a name is kept: later ones are theme overrides,
    which are checked separately via :func:`parse_oklch_tokens` rather than
    silently folded in here.
    """
    tokens: Dict[str, str] = {}
    for name, value in _HEX_DECL.findall(css):
        tokens.setdefault(name, value.lower())
    return tokens


def parse_oklch_tokens(css: str) -> Dict[str, str]:
    """Map token name -> hex equivalent for every ``oklch()`` custom property (#12922).

    These are the wide-gamut overrides. They were previously reported as
    unchecked, which is how #12915's sRGB fix left the same failing pair
    shipping on P3 displays. Converted to sRGB so they can be measured on the
    same footing as the hex block.
    """
    tokens: Dict[str, str] = {}
    for name, value in _ANY_COLOR_DECL.findall(css):
        if "oklch" not in value.lower():
            continue
        converted = oklch_to_hex(value)
        if converted:
            tokens.setdefault(name, converted)
    return tokens


def parse_non_hex_tokens(css: str) -> Dict[str, str]:
    """Colour tokens defined in a format this checker cannot evaluate."""
    skipped: Dict[str, str] = {}
    covered = set(parse_hex_tokens(css)) | set(parse_oklch_tokens(css))
    for name, value in _ANY_COLOR_DECL.findall(css):
        if name not in covered:
            skipped.setdefault(name, value.strip())
    return skipped



_OKLCH_DECL = re.compile(r"oklch\(\s*([\d.]+)%\s+([\d.]+)\s+([\d.]+)\s*\)", re.IGNORECASE)


def oklch_to_hex(value: str) -> str | None:
    """Convert a CSS ``oklch(L% C H)`` colour to ``#rrggbb`` (#12922).

    The wide-gamut block re-declares the same semantic pairs in oklch, so a
    hex-only checker reported them as unchecked and #12915's fix covered the
    sRGB path only — leaving white-on-green still shipping on P3 displays.

    Conversion is the standard oklab pipeline: oklch -> oklab -> linear sRGB ->
    gamma-encoded sRGB. Out-of-gamut components are clamped, which is what a
    browser does when rendering an oklch colour on an sRGB display, so the ratio
    computed here matches what an sRGB viewer actually sees. Returns ``None``
    when *value* is not an oklch literal.
    """
    match = _OKLCH_DECL.search(value)
    if not match:
        return None

    lightness = float(match.group(1)) / 100.0
    chroma = float(match.group(2))
    hue = math.radians(float(match.group(3)))

    a = chroma * math.cos(hue)
    b = chroma * math.sin(hue)

    l_ = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3

    linear = (
        4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
        -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
        -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_,
    )

    channels = []
    for c in linear:
        c = max(0.0, min(1.0, c))
        c = 1.055 * (c ** (1 / 2.4)) - 0.055 if c > 0.0031308 else 12.92 * c
        channels.append(round(max(0.0, min(1.0, c)) * 255))
    return "#%02x%02x%02x" % tuple(channels)

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
    oklch_tokens = parse_oklch_tokens(css)
    skipped = parse_non_hex_tokens(css)

    # #12922: the wide-gamut block re-declares the same semantic pairs in
    # oklch. Those overrides shadow names already present in the hex map, so
    # they were not even reaching the "unchecked" list — they were invisible.
    # Both themes are now measured, because a P3 display renders the second set.
    themes = [("sRGB", tokens)]
    if oklch_tokens:
        merged = {**tokens, **oklch_tokens}
        themes.append(("wide-gamut (oklch)", merged))

    print(f"[contrast] {css_path.relative_to(REPO_ROOT)}")
    print(
        f"[contrast] {len(tokens)} hex tokens, {len(oklch_tokens)} oklch overrides, "
        f"{len(skipped)} tokens still unchecked"
    )

    failures = []
    for theme_name, theme_tokens in themes:
        theme_pairs = build_pairs(theme_tokens)
        print(f"[contrast] -- {theme_name}: {len(theme_pairs)} derived pairs")
        for fg, bg, required in theme_pairs:
            ratio = contrast_ratio(theme_tokens[fg], theme_tokens[bg])
            ok = ratio >= required
            marker = "ok  " if ok else "FAIL"
            print(f"  {marker} {ratio:5.2f}:1 (need {required})  {fg} on {bg}")
            if not ok:
                failures.append((f"[{theme_name}] {fg}", bg, ratio, required))

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
