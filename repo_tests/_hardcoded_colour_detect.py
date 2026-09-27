# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
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
from pathlib import Path

from repo_tests._hardcoded_colour_baseline import (
    EXEMPT_BASENAMES,
)
from repo_tests._reach import declare

_FRONTEND = Path("autobot-frontend/src")
_SUFFIXES = {".ts", ".vue", ".js"}
_SKIP_FRAGMENTS = (
    "assets/css/",
    "assets/tokens.css",
    "assets/tailwind.css",
    "design-tokens/",
    "design-system/",
    "types/generated/",
)
_HEX = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})\b")
_CONTEXT = re.compile(
    r"colou?r|background|fill|stroke|border|shadow|palette|theme|rgb|gradient|swatch|hsl",
    re.IGNORECASE,
)
_STYLE_BLOCK = re.compile(r"<style\b[^>]*>.*?</style>", re.DOTALL | re.IGNORECASE)
_RESOLVED = re.compile(
    r"getCssVar\s*\(\s*['\"]--[^'\"]+['\"]\s*,\s*['\"](#[0-9a-fA-F]{3,8})['\"]"
    r"|var\(\s*--[A-Za-z0-9_-]+\s*,\s*(#[0-9a-fA-F]{3,8})\s*\)"
)
_VALUE_POSITION = re.compile(r"""(?::|['"`])\s*$""")
_OPEN_VALUE = re.compile(r"[:,(\[]\s*$")
_COMMENT_BEFORE = re.compile(r"(?://|/\*|\*|<!--|#)\s")


def _is_colour(token: str, line: str = "", start: int = -1) -> bool:
    """Whether *token* is a colour rather than an issue reference.

    A hex carrying `a-f`, or of a length no issue number uses, is a colour on
    its face. A digit-only short literal -- `#000`, `#1234` -- is valid CSS and
    indistinguishable from an issue number by shape alone, so it is decided by
    POSITION: counted when it sits where a value goes, ignored when it sits in
    prose. Rejecting every digit-only short value, as the first version did,
    silently exempted `color: '#000'`.
    """
    digits = token[1:]
    if re.search("[a-fA-F]", digits) or len(digits) in (6, 8):
        return True
    if len(digits) not in (3, 4) or start < 0:
        return False
    before = line[:start]
    if _COMMENT_BEFORE.search(before):
        return False
    return bool(_VALUE_POSITION.search(before))


def _colour_scanned_files(root: Path) -> list[str]:
    """Every file the colour scanner opens. Its reach population."""
    frontend = root / _FRONTEND
    if not frontend.is_dir():
        return []
    out: list[str] = []
    for path in sorted(frontend.rglob("*")):
        if path.suffix not in _SUFFIXES or "node_modules" in path.parts:
            continue
        rel = path.relative_to(frontend).as_posix()
        if any(fragment in rel for fragment in _SKIP_FRAGMENTS):
            continue
        if path.name in EXEMPT_BASENAMES:
            continue
        if "__tests__" in path.parts or path.name.endswith((".spec.ts", ".test.ts", ".stories.ts")):
            continue
        out.append(rel)
    return out


def _important_scanned_files(root: Path) -> list[str]:
    """Every .vue the !important sweep opens. Its reach population."""
    frontend = root / _FRONTEND
    if not frontend.is_dir():
        return []
    return [
        p.relative_to(frontend).as_posix() for p in sorted(frontend.rglob("*.vue")) if "node_modules" not in p.parts
    ]


REACH_COLOUR_FILES = declare(
    "hardcoded-colour-scan",
    discover=_colour_scanned_files,
    floor=820,
    growth=60,
    skips=0,
    what="frontend source files scanned for colour literals",
)
REACH_IMPORTANT_FILES = declare(
    "important-declaration-sweep",
    discover=_important_scanned_files,
    floor=430,
    growth=40,
    skips=0,
    what="component files scanned for !important",
)


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
        # Blank each resolved fallback AT ITS OWN SPAN, preserving length, rather
        # than counting them file-wide and subtracting. A file-wide subtraction
        # let `getCssVar('--accent', '#ff00aa')` on one line cancel a bare
        # `background: '#ff00aa'` on another, so adding a hardcoded colour beside
        # a correctly-resolved one of the same value passed the ratchet.
        text = _RESOLVED.sub(lambda m: "_" * len(m.group(0)), text)
        # Context carries onto the next line. A property whose value sits below
        # it -- `color:\n  '#ff00aa'` -- puts the keyword and the literal on
        # different lines, and a strictly per-line test matched the first and
        # scanned the second without context, so the colour was invisible.
        carry = False
        for line in text.splitlines():
            has_context = _CONTEXT.search(line) or carry
            carry = bool(_CONTEXT.search(line)) and bool(_OPEN_VALUE.search(line))
            if not has_context:
                continue
            for match in _HEX.finditer(line):
                if not _is_colour(match.group(0), line, match.start()):
                    continue
                literal = match.group(0).lower()
                counts[literal] = counts.get(literal, 0) + 1
    return counts


_STYLE_CONTENT = re.compile(r"<style\b[^>]*>(.*?)</style>", re.DOTALL | re.IGNORECASE)
_IMPORTANT = re.compile(r"!\s*important", re.IGNORECASE)
_THEME_SOURCES = (
    "assets/css/design-tokens.css",
    "assets/css/themes/light.css",
    "assets/css/themes/dark.css",
)


def _scan_important(root: Path) -> dict[str, int]:
    """``path -> !important declarations`` inside component ``<style>`` blocks.

    Keyed by path because `!important` has no value to key on. Files are reached
    by GLOB rather than named as literals, so this does not add a concrete
    dependency the python path filter would have to cover.
    """
    counts: dict[str, int] = {}
    for path in sorted(root.rglob("*.vue")):
        if "node_modules" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        css = "\n".join(m.group(1) for m in _STYLE_CONTENT.finditer(text))
        found = len(_IMPORTANT.findall(css))
        if found:
            counts[path.relative_to(root).as_posix()] = found
    return counts


_DECLARATION = re.compile(r"(?:^|[{;])\s*(--[A-Za-z0-9_-]+)\s*:", re.MULTILINE)
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_ANY_DECLARATION = re.compile(r"(--[A-Za-z0-9_-]+)\s*:")


def _component_style_blocks(root: Path) -> list[tuple[str, int]]:
    """Every component ``<style>`` block the sweep reads. The reach population.

    NOT the theme-name count: those come from three CSS files, so a floor on
    them stays satisfied even if every component were skipped, and "zero
    clashes" would then mean "nothing was read" (#17567).
    """
    found: list[tuple[str, int]] = []
    frontend = root / _FRONTEND
    if not frontend.is_dir():
        return found
    for path in sorted(frontend.rglob("*.vue")):
        if "node_modules" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for index, _ in enumerate(_STYLE_CONTENT.finditer(text)):
            found.append((path.relative_to(frontend).as_posix(), index))
    return found


REACH_STYLE_BLOCKS = declare(
    "component-style-block-sweep",
    discover=_component_style_blocks,
    floor=380,
    growth=40,
    skips=0,
    what="component <style> blocks searched for design-token redefinitions",
)


def _owned_token_names(root: Path) -> set[str]:
    """Every custom property the design system declares."""
    owned: set[str] = set()
    for name in _THEME_SOURCES:
        source = root / name
        assert source.is_file(), f"{name} has moved; this assertion reads it by path"
        owned |= set(_ANY_DECLARATION.findall(source.read_text(encoding="utf-8")))
    return owned


def _token_redefinitions(root: Path, owned: set[str]) -> tuple[dict[str, list[str]], int]:
    """``(component -> theme tokens it redefines, style blocks parsed)``.

    Returns the reach alongside the finding, because "no component redefines a
    token" and "no component was read" produce the same empty dict.
    """
    offenders: dict[str, list[str]] = {}
    blocks = 0
    for path in sorted(root.rglob("*.vue")):
        if "node_modules" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        found = list(_STYLE_CONTENT.finditer(text))
        blocks += len(found)
        css = _CSS_COMMENT.sub(" ", "\n".join(m.group(1) for m in found))
        clashes = sorted({n for n in _DECLARATION.findall(css) if n in owned})
        if clashes:
            offenders[path.relative_to(root).as_posix()] = clashes
    return offenders, blocks
