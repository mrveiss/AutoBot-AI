# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Generate the GitHub social preview cards for the two skills marketplaces.

A social preview is a repository *setting*, not a file GitHub reads from the tree,
and there is no REST or GraphQL endpoint for it. So the cards are authored here --
where they get review and version history -- and uploaded by hand exactly once, the
same author-here / deploy-elsewhere split used for the root landing page.

Palette and type follow ``site/mrveiss.github.io/index.html`` so a pasted repository
link reads as the same property as the site.

The cards carry no counts, metrics or badges on purpose: a number baked into a
setting nobody revisits becomes false the first time a skill is added, and these
repositories are about working honestly. They name domains instead.

Fonts are not vendored. See README.md for the three files to fetch and where to put
them; this module never makes a network call.

Usage:
    python3 make_cards.py --fonts ./fonts --out .
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1280, 640
MARGIN = 88
RULE_Y = 430

# Dark-theme tokens from the landing page.
BG = "#1e1418"  # plum-950
SUNKEN = "#150d11"  # plum-975
BORDER = "#402c34"  # plum-800
CREAM = "#f1e8de"  # plum-cream
MUTED = "#b3a596"
SUBTLE = "#82737a"
ACCENT = "#e2842e"  # orange-400

EYEBROW = "CLAUDE CODE  ·  PLUGIN MARKETPLACE"
LICENCE = "Apache-2.0"

CARDS = [
    {
        "out": "claude-dev-skills-card.png",
        "title": "How to work, ",
        "accent": "installable.",
        "sub": "Claude Code skills that encode the practice, not the project.",
        "detail": ("process  ·  review lenses  ·  UI design  ·  " "auditing  ·  commits  ·  memory hygiene"),
        "command": "/plugin marketplace add mrveiss/Claude-Dev-Skills",
    },
    {
        "out": "autobot-dev-skills-card.png",
        "title": "The AutoBot ",
        "accent": "workflow.",
        "sub": "One install gives every platform developer the same setup.",
        "detail": ("implement  ·  review  ·  pre-merge validation  ·  " "full-stack debugging  ·  backlog drain"),
        "command": "/plugin marketplace add mrveiss/AutoBot-AI-Claude-dev-skills",
    },
]


def _font(fonts: Path, name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(fonts / f"{name}.ttf"), size)


def _tracked(draw, xy, text, font, fill, tracking) -> None:
    """Draw letter-spaced text; Pillow has no tracking of its own."""
    x, y = xy
    for char in text:
        draw.text((x, y), char, font=font, fill=fill)
        x += draw.textlength(char, font=font) + tracking


def _accent_mark(draw) -> None:
    """The site favicon's disc, bled off the top-right corner as concentric rings."""
    draw.ellipse([WIDTH - 150, -150, WIDTH + 150, 150], fill=ACCENT)
    draw.ellipse([WIDTH - 132, -132, WIDTH + 132, 132], fill=BG)
    draw.ellipse([WIDTH - 96, -96, WIDTH + 96, 96], fill=ACCENT)


def _draw_headline(draw, spec: dict, fonts: Path) -> None:
    _tracked(draw, (MARGIN, 92), EYEBROW, _font(fonts, "JetBrainsMono", 21), SUBTLE, 3.2)

    display = _font(fonts, "Fraunces", 82)
    draw.text((MARGIN, 158), spec["title"], font=display, fill=CREAM)
    offset = MARGIN + draw.textlength(spec["title"], font=display)
    draw.text((offset, 158), spec["accent"], font=display, fill=ACCENT)

    draw.text((MARGIN, 274), spec["sub"], font=_font(fonts, "Schibsted", 37), fill=MUTED)
    draw.text((MARGIN, 336), spec["detail"], font=_font(fonts, "Schibsted", 25), fill=SUBTLE)


def _draw_install(draw, spec: dict, fonts: Path) -> None:
    """The hairline separates what this is from how you install it.

    The licence rides above the rule as a caption rather than beside the chip, so it
    cannot crowd the longer of the two commands.
    """
    caption = _font(fonts, "JetBrainsMono", 19)
    draw.text(
        (WIDTH - MARGIN - draw.textlength(LICENCE, font=caption), RULE_Y - 30),
        LICENCE,
        font=caption,
        fill=SUBTLE,
    )
    draw.line([MARGIN, RULE_Y, WIDTH - MARGIN, RULE_Y], fill=BORDER, width=2)

    mono = _font(fonts, "JetBrainsMono", 25)
    pad_x, pad_y = 26, 20
    chip_w = draw.textlength(spec["command"], font=mono) + pad_x * 2
    chip_h = 25 + pad_y * 2 + 6
    top = RULE_Y + 42
    draw.rounded_rectangle(
        [MARGIN, top, MARGIN + chip_w, top + chip_h],
        radius=12,
        fill=SUNKEN,
        outline=BORDER,
        width=2,
    )
    draw.text((MARGIN + pad_x, top + pad_y - 2), spec["command"], font=mono, fill=CREAM)


def render_card(spec: dict, fonts: Path, out_dir: Path) -> Path:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    _accent_mark(draw)
    _draw_headline(draw, spec, fonts)
    _draw_install(draw, spec, fonts)

    path = out_dir / spec["out"]
    image.save(path, "PNG", optimize=True)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fonts", type=Path, default=Path(__file__).parent / "fonts")
    parser.add_argument("--out", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()

    for spec in CARDS:
        render_card(spec, args.fonts, args.out)


if __name__ == "__main__":
    main()
