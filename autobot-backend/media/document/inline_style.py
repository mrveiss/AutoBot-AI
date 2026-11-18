# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Whether an element's inline ``style`` hides it from a reader (#18826).

A page can carry text no reader sees -- ``display:none``, zero-size text, the
"screen-reader only" clip patterns -- and an extractor that keeps it hands that text
to the knowledge base and the model: a prompt-injection path. The HTML extractor
drops such an element together with its text.

The declarations are parsed, not pattern-matched on the raw attribute: comments are
removed, ``;`` splits only outside quotes and parentheses, property names are
case-insensitive, whitespace is tolerated, and the cascade inside one attribute is
honoured -- an ``!important`` declaration beats a normal one, and among equals the
last wins. So ``display:none!important;display:block`` is hidden, as a browser renders it.

Hidden when the effective declarations say:

- ``display: none``; ``visibility: hidden | collapse``;
- ``font-size: 0`` in any unit, or a ``font`` shorthand whose size is zero (``font: 0/0 a``);
- ``opacity: 0`` (or ``0%``);
- ``clip: rect(...)`` enclosing no area (``rect(0 0 0 0)``, ``rect(1px,1px,1px,1px)``);
- ``clip-path: inset(...)`` insetting opposite sides by 100% or more (``inset(50%)``);
- ``width`` and ``height`` both at most 1px with ``overflow: hidden | clip``;
- ``position: absolute | fixed`` with ``left``/``top``/``right``/``bottom`` at or below
  -1000px (or -100em/rem), and ``text-indent`` at or below the same offset.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from autobot_shared.env_utils import env_int_clamped

#: Longest inline ``style`` attribute parsed, in characters (#18826). A longer one is treated as
#: hiding its element (fail closed): truncating instead would let padding push ``display:none``
#: past the cut, and no legitimate page needs a style attribute this long.
STYLE_MAX_CHARS = env_int_clamped("AUTOBOT_HTML_STYLE_MAX_CHARS", 4096, min_v=256, max_v=65536)
_IMPORTANT = re.compile(r"!\s*important\s*$", re.IGNORECASE)
_LENGTH = re.compile(r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+))([a-z%]*)$")  # unambiguous: no \d+\d* split
_FUNCTION_ARGS = re.compile(r"^([a-z-]+)\((.*)\)$", re.DOTALL)
#: An offset at or beyond this many pixels (16px per em) places content off-screen.
_OFFSCREEN_PX = -1000.0
_PX_PER_EM = 16.0
_OFFSET_PROPERTIES = ("left", "top", "right", "bottom")


def _strip_comments(style: str) -> str:
    """Remove ``/* ... */`` comments in one linear pass; an unterminated comment drops the tail.

    A lazy ``.*?`` comment regex is quadratic on an unterminated comment (``'/*a' * 40000`` took ~48s),
    so the scan uses ``str.find`` twice per comment instead (#18826).
    """
    out, i = [], 0
    while True:
        start = style.find("/*", i)
        if start < 0:
            out.append(style[i:])
            return " ".join(out)
        out.append(style[i:start])
        end = style.find("*/", start + 2)
        if end < 0:
            return " ".join(out)
        i = end + 2


def _split_declarations(style: str) -> List[str]:
    """Split *style* on ``;`` outside quotes and parentheses."""
    parts, current, depth, quote = [], [], 0, ""
    for char in _strip_comments(style):
        if quote:
            quote = "" if char == quote else quote
        elif char in "\"'":
            quote = char
        elif char in "()":
            depth = max(0, depth + (1 if char == "(" else -1))
        elif char == ";" and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return parts


def parse_declarations(style: str) -> Dict[str, str]:
    """The effective ``property -> value`` map of an inline style; values lowercased, whitespace collapsed."""
    effective: Dict[str, Tuple[bool, str]] = {}
    for declaration in _split_declarations(style or ""):
        name, sep, value = declaration.partition(":")
        name = name.strip().lower()
        if not sep or not name:
            continue
        important = bool(_IMPORTANT.search(value))
        value = re.sub(r"\s+", " ", _IMPORTANT.sub("", value)).strip().lower()
        previous = effective.get(name)
        if previous is None or important or not previous[0]:
            effective[name] = (important, value)
    return {name: value for name, (_important, value) in effective.items()}


def _length(value: str) -> Optional[Tuple[float, str]]:
    """``(number, unit)`` of a CSS length or percentage, else ``None``."""
    match = _LENGTH.match((value or "").strip())
    return (float(match.group(1)), match.group(2)) if match else None


def _is_zero(value: str) -> bool:
    length = _length(value)
    return length is not None and length[0] == 0


def _pixels(value: str) -> Optional[float]:
    """A length in px (em/rem at 16px, unitless only when zero), else ``None``."""
    length = _length(value)
    if length is None:
        return None
    number, unit = length
    if unit == "px" or (unit == "" and number == 0):
        return number
    return number * _PX_PER_EM if unit in ("em", "rem") else None


def _function_args(value: str, name: str) -> Optional[List[str]]:
    """Arguments of ``name(...)`` split on commas and whitespace, else ``None``."""
    match = _FUNCTION_ARGS.match(value or "")
    if not match or match.group(1) != name:
        return None
    return [arg for arg in re.split(r"[\s,]+", match.group(2)) if arg]


def _empty_clip(value: str) -> bool:
    """``rect(top, right, bottom, left)`` with no area between its edges."""
    args = _function_args(value, "rect")
    if not args or len(args) != 4:
        return False
    top, right, bottom, left = (_pixels(arg) for arg in args)
    if None in (top, right, bottom, left):
        return False
    return bottom <= top or right <= left


def _four_sides(args: List[str]) -> List[str]:
    """Expand a 1-4 value box shorthand to ``[top, right, bottom, left]``."""
    if len(args) == 1:
        return args * 4
    if len(args) == 2:
        return [args[0], args[1], args[0], args[1]]
    if len(args) == 3:
        return [args[0], args[1], args[2], args[1]]
    return args[:4]


def _percent(value: str) -> Optional[float]:
    """A percentage (a bare zero counts as 0%), else ``None``."""
    length = _length(value)
    if length is None or not (length[1] == "%" or (length[1] == "" and length[0] == 0)):
        return None
    return length[0]


def _empty_inset(value: str) -> bool:
    """``inset(...)`` whose opposite insets meet or cross (each side a percentage or zero)."""
    args = _function_args(value, "inset")
    if not args:
        return False
    args = args[: args.index("round")] if "round" in args else args
    percents = [_percent(side) for side in _four_sides(args)] if args else []
    if not percents or None in percents:
        return False
    top, right, bottom, left = percents
    return top + bottom >= 100 or left + right >= 100


def _zero_font(decls: Dict[str, str]) -> bool:
    if _is_zero(decls.get("font-size", "")):
        return True
    # In the ``font`` shorthand the size is the only bare length; ``/line-height`` stays attached to its slash.
    return any(_is_zero(token) for token in decls.get("font", "").replace("/", " /").split())


def _tiny_box(decls: Dict[str, str]) -> bool:
    if decls.get("overflow") not in ("hidden", "clip"):
        return False
    width, height = _pixels(decls.get("width", "")), _pixels(decls.get("height", ""))
    return width is not None and height is not None and width <= 1 and height <= 1


def _offscreen(decls: Dict[str, str]) -> bool:
    indent = _pixels(decls.get("text-indent", ""))
    if indent is not None and indent <= _OFFSCREEN_PX:
        return True
    if decls.get("position") not in ("absolute", "fixed"):
        return False
    offsets = (_pixels(decls.get(name, "")) for name in _OFFSET_PROPERTIES)
    return any(offset is not None and offset <= _OFFSCREEN_PX for offset in offsets)


def _invisible(decls: Dict[str, str]) -> bool:
    opacity = _length(decls.get("opacity", ""))
    return (
        decls.get("display") == "none"
        or decls.get("visibility") in ("hidden", "collapse")
        or (opacity is not None and opacity[0] <= 0 and opacity[1] in ("", "%"))
    )


def hidden_by_style(style: str) -> bool:
    """Whether the inline *style* hides its element's content from a reader."""
    if not style:
        return False
    if len(style) > STYLE_MAX_CHARS:
        return True  # fail closed: see STYLE_MAX_CHARS
    decls = parse_declarations(style)
    return (
        _invisible(decls)
        or _zero_font(decls)
        or _empty_clip(decls.get("clip", ""))
        or _empty_inset(decls.get("clip-path", ""))
        or _tiny_box(decls)
        or _offscreen(decls)
    )
