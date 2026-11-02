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

    --text-on-<x>  against  --color-<x>          (foreground on a semantic fill;
                                                  --color-<x>-solid for a status <x>
                                                  that declares one, #19872)
    --text-<y>     against  --bg-primary         (body text on the app background)

Status pairs (success/warning/error/info) are held to 4.5:1 and are checked in
*every theme that repaints them*, not only the default ``:root`` (#19872).
A theme's tokens are the cascade of the blocks that apply to it, so ember-dark's
``--text-on-error`` is measured against ember-dark's ``--color-error``. See
``THEMES``. A block that declares a status token but belongs to no modelled
theme fails the run, so a new theme cannot opt out of the gate by omission.

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

# Status fills carry real label text (badges, buttons, toasts), so they are held
# to the normal-text ratio, not the large-text one (#19872).
STATUS_SEMANTICS = ("success", "warning", "error", "info")

# Error and info keep white label text on a darker solid-fill shade of the same
# hue (``--color-error-solid``): ``--color-error`` / ``--color-info`` themselves
# stay the text, border and icon colour. These two must declare ``-solid`` in
# every theme (a theme without it fails). Success and warning use dark ink on
# their own fill; they are measured against ``-solid`` only if a theme declares one.
SOLID_REQUIRED = ("error", "info")

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
        if semantic in STATUS_SEMANTICS and f"{background}-solid" in tokens:
            background = f"{background}-solid"
        if background in tokens:
            # Status fills carry real label text (#19872); other fills (primary)
            # stay at the large-text/UI-component threshold.
            pairs.append((name, background, AA_NORMAL if semantic in STATUS_SEMANTICS else AA_LARGE))

    for text_token in _BODY_TEXT_TOKENS:
        if text_token in tokens and _BODY_BACKGROUND in tokens:
            pairs.append((text_token, _BODY_BACKGROUND, AA_NORMAL))

    return pairs


# --------------------------------------------------------------------------
# Per-theme status pairs (#19872)
# --------------------------------------------------------------------------

FRONTEND_CSS = REPO_ROOT / "autobot-frontend" / "src" / "assets" / "css"
SLM_CSS = REPO_ROOT / "autobot-slm-frontend" / "src" / "assets" / "styles"
KIT_TOKENS = REPO_ROOT / "libs" / "autobot-ui" / "src" / "tokens"

_DECL = re.compile(r"(--[a-zA-Z0-9-]+)\s*:\s*([^;{}]+);")
_VAR = re.compile(r"^var\(\s*(--[a-zA-Z0-9-]+)\s*(?:,\s*(.+))?\)$")
_HEX_VALUE = re.compile(r"^#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?([0-9a-fA-F]{2})?$")
_STATUS_TOKEN = re.compile(r"^--(?:aui-)?(?:color|text-on)-(?:success|warning|error|info)(?:-contrast|-solid)?$")


def _strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)


def parse_blocks(css: str) -> List[Tuple[str, str, Dict[str, str]]]:
    """Flatten *css* into ``(selector, enclosing_at_rules, declarations)``.

    Nested rules are hoisted with the text of their at-rule ancestors, so
    ``@supports (color: oklch(...)) { :root { ... } }`` comes back as selector
    ``:root`` with at-rules ``@supports (color: oklch(...))``. A later
    declaration of a name inside one block wins, as in the cascade.
    """
    css = _strip_comments(css)
    stack: List[List[str]] = []  # [selector, body_text]
    blocks: List[Tuple[str, str, Dict[str, str]]] = []
    buf = ""
    for ch in css:
        if ch == "{":
            head, sep, own = buf.rpartition(";")
            if stack:
                stack[-1][1] += head + sep
            stack.append([" ".join(own.split()), ""])
            buf = ""
        elif ch == "}":
            if stack:
                selector, body = stack.pop()
                at_rules = " ".join(f[0] for f in stack if f[0].startswith("@"))
                blocks.append((selector, at_rules, dict(_DECL.findall(body + buf))))
            buf = ""
        else:
            buf += ch
    return blocks


def _literal_colour(value: str) -> str | None:
    if _HEX_VALUE.match(value):
        return value.lower()
    return oklch_to_hex(value)


def resolve_colour(name: str, decls: Dict[str, str], _seen: Tuple[str, ...] = ()) -> str | None:
    """Resolve token *name* through ``var()`` chains to a hex colour; None if unevaluable."""
    if name in _seen or name not in decls:
        return None
    value = " ".join(decls[name].split())
    var = _VAR.match(value)
    if not var:
        return _literal_colour(value)
    target = resolve_colour(var.group(1), decls, _seen + (name,))
    if target is None and var.group(2):
        return _literal_colour(var.group(2).strip())
    return target


class ThemeSpec:
    """One renderable theme: its name, the blocks that cascade into it, its token naming."""

    def __init__(self, name, layers, fill="--color-{s}", on="--text-on-{s}"):
        self.name, self.layers, self.fill, self.on = name, layers, fill, on


def _layer(path: Path, selector: str, at_rule: str = "") -> Tuple[Path, str, str]:
    """A block *selector* in *path* whose at-rule ancestry contains *at_rule* ('' = none)."""
    return (path, selector, at_rule)


_BASE = FRONTEND_CSS / "design-tokens.css"
_EMBER = FRONTEND_CSS / "themes" / "ember.css"
_TEMPLATE = FRONTEND_CSS / "themes" / "_template.css"
_EMBER_SEL = '[data-theme-variant="ember"]'
_NOT_CONTRAST_MONO = ':where(:not([data-theme="contrast"], [data-theme="mono"]))'
_EMBER_LIGHT_SELECTOR = f'{_EMBER_SEL}:root{_NOT_CONTRAST_MONO}, {_EMBER_SEL}[data-theme="light"]'
_BASE_LAYERS = [_layer(_BASE, ":root")]
_EMBER_COMMON = [_layer(_EMBER, ":root"), _layer(_EMBER, _EMBER_SEL + _NOT_CONTRAST_MONO)]

# light, dark, contrast, mono and the accents inherit every status token from the
# base :root (their theme files declare none); unmodelled_status_blocks() fails
# the run if one starts to.
THEMES: List[ThemeSpec] = [
    ThemeSpec("default (light, dark, contrast, mono, accents)", _BASE_LAYERS),
    ThemeSpec("default, wide-gamut (oklch)", _BASE_LAYERS + [_layer(_BASE, ":root", "oklch")]),
    ThemeSpec(
        "ember-light",
        _BASE_LAYERS + _EMBER_COMMON + [_layer(_EMBER, _EMBER_LIGHT_SELECTOR)],
    ),
    ThemeSpec("ember-dark", _BASE_LAYERS + _EMBER_COMMON + [_layer(_EMBER, _EMBER_SEL + '[data-theme="dark"]')]),
    ThemeSpec("custom template", _BASE_LAYERS + [_layer(_TEMPLATE, '[data-theme="custom"]')]),
    ThemeSpec(
        "slm (all schemes)",
        [
            _layer(SLM_CSS / "main.css", "@theme"),
            _layer(SLM_CSS / "main.css", ":root"),
            _layer(SLM_CSS / "slm-scheme.css", ":root"),
        ],
    ),
    ThemeSpec(
        "kit contract fallback",
        [_layer(KIT_TOKENS / "contract.css", ":root")],
        fill="--aui-color-{s}",
        on="--aui-color-{s}-contrast",
    ),
]

# Files scanned for status-token declarations that no THEMES entry models.
_SCANNED_FILES = (
    [_BASE]
    + sorted((FRONTEND_CSS / "themes").glob("*.css"))
    + [SLM_CSS / "main.css", SLM_CSS / "slm-scheme.css", KIT_TOKENS / "contract.css"]
)


def _layer_applies(block: Tuple[str, str], layer: Tuple[Path, str, str]) -> bool:
    selector, at = block
    _, wanted, at_rule = layer
    if selector != wanted and not (wanted == "@theme" and selector.startswith("@theme")):
        return False
    return (at_rule in at) if at_rule else not at


def theme_declarations(theme: ThemeSpec, cache: Dict[Path, List] | None = None) -> Dict[str, str]:
    """Cascade the blocks of *theme* in layer order; later layers win."""
    cache = cache if cache is not None else {}
    decls: Dict[str, str] = {}
    for layer in theme.layers:
        path = layer[0]
        if path not in cache:
            cache[path] = parse_blocks(path.read_text(encoding="utf-8"))
        for selector, at, body in cache[path]:
            if _layer_applies((selector, at), layer):
                decls.update(body)
    return decls


def unmodelled_status_blocks(themes: List[ThemeSpec] = THEMES, files: List[Path] = _SCANNED_FILES) -> List[str]:
    """Blocks declaring a status token that no theme models (a theme escaping the gate)."""
    found = []
    for path in files:
        for selector, at, body in parse_blocks(path.read_text(encoding="utf-8")):
            if not any(_STATUS_TOKEN.match(n) for n in body):
                continue
            covered = any(
                _layer_applies((selector, at), layer) and layer[0] == path for t in themes for layer in t.layers
            )
            if not covered:
                found.append(f"{path.relative_to(REPO_ROOT)}: {selector} {at}".rstrip())
    return found


def _check_hover_pair(theme, decls, on_tok, on_hex, fill_tok, fill_hex, required, lines, failures) -> None:
    """Measure the on-status text against ``<fill>-hover`` when a theme declares one (#19953).

    A hover fill must keep the same AA ratio as the resting fill, and must differ from it
    (a hover token equal to the resting fill is the no-feedback defect it exists to fix).
    """
    hover_tok = f"{fill_tok}-hover"
    if hover_tok not in decls:
        return
    hover_hex = resolve_colour(hover_tok, decls)
    if hover_hex is None:
        lines.append(f"  FAIL   n/a    {on_tok} on {hover_tok}")
        failures.append(f"{theme.name}: cannot evaluate {on_tok} on {hover_tok}")
        return
    ratio = contrast_ratio(on_hex, hover_hex)
    ok = ratio >= required and hover_hex != fill_hex
    lines.append(
        f"  {'ok  ' if ok else 'FAIL'} {ratio:5.2f}:1 (need {required})  {on_tok} {on_hex} on {hover_tok} {hover_hex}"
    )
    if ratio < required:
        failures.append(f"{theme.name}: {on_tok} on {hover_tok} = {ratio:.2f}:1 < {required}")
    if hover_hex == fill_hex:
        failures.append(f"{theme.name}: {hover_tok} equals {fill_tok} ({fill_hex}); hover gives no feedback")


def check_status_themes(themes: List[ThemeSpec] = THEMES, required: float = AA_NORMAL) -> Tuple[List[str], List[str]]:
    """Return ``(report_lines, failure_lines)`` for every theme's on-status pairs."""
    lines: List[str] = []
    failures: List[str] = []
    cache: Dict[Path, List] = {}
    for theme in themes:
        decls = theme_declarations(theme, cache)
        lines.append(f"[contrast] -- status pairs: {theme.name}")
        for semantic in STATUS_SEMANTICS:
            on_tok, fill_tok = theme.on.format(s=semantic), theme.fill.format(s=semantic)
            solid_tok = f"{fill_tok}-solid"
            if semantic in SOLID_REQUIRED or solid_tok in decls:
                fill_tok = solid_tok
            on_hex, fill_hex = resolve_colour(on_tok, decls), resolve_colour(fill_tok, decls)
            if on_hex is None or fill_hex is None:
                lines.append(f"  FAIL   n/a    {on_tok} on {fill_tok}")
                failures.append(f"{theme.name}: cannot evaluate {on_tok} on {fill_tok} ({on_hex} on {fill_hex})")
                continue
            ratio = contrast_ratio(on_hex, fill_hex)
            ok = ratio >= required
            lines.append(
                f"  {'ok  ' if ok else 'FAIL'} {ratio:5.2f}:1 (need {required})  "
                f"{on_tok} {on_hex} on {fill_tok} {fill_hex}"
            )
            if not ok:
                failures.append(f"{theme.name}: {on_tok} on {fill_tok} = {ratio:.2f}:1 < {required}")
            _check_hover_pair(theme, decls, on_tok, on_hex, fill_tok, fill_hex, required, lines, failures)
    return lines, failures


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

    status_lines, status_failures = check_status_themes()
    print("\n".join(status_lines))
    for entry in unmodelled_status_blocks():
        status_failures.append(f"status token declared outside every modelled theme: {entry}")
    failures.extend((msg, "", 0.0, 0.0) for msg in status_failures)

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
            print(f"    {fg} on {bg}: {ratio:.2f}:1 < {required}" if bg else f"    {fg}")
        if not args.report:
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
