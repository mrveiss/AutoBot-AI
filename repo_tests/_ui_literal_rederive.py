# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A second derivation of the template-text and attribute literals (#12732).

`_ui_literal_scan.py` enumerates by walking the filesystem and reads the
template with `html.parser`. This module shares neither: it enumerates with
git's index via `tools.lint._scan_helpers.tracked_paths` (environment scrubbed there)
and matches with regexes over the template with comments removed. The ratchet
test compares the two as SETS of (file, kind, literal).

The regexes are a narrower predicate than the parser's, on purpose -- they were
the first prototype -- so the comparison is not expected to be empty. Every
difference is either a detector fix or one of the enumerated, justified
exclusions below, each a predicate over the literal and its source -- never a
list of names:

Found by the regexes and not by the parser (`explain_regex_only`):

* `opaque-element`: the regex hit's OFFSET lies inside a `<code>`, `<pre>`,
  `<svg>` or `<path>` element, whose content is a file name, a command or a
  drawing, not translatable prose (every occurrence the regex found, not a
  substring test over the file);
* `below-minimum`: under the parser's 4-character floor (`Vue`, `Git`, `Ask`);
* `identifier-shaped`: CamelCase or snake/kebab, i.e. a name (`AutoBot`,
  `updated_at`, `autobot-backend`), which the parser does not call prose;
* `url-shaped`: begins `http://`, `https://` or `/`, a value rather than text.

Found by the parser and not by the regexes (`explain_parser_only`):

* `outside-regex-class`: contains a character the prototype regex's class
  cannot hold (digits, `&`, `:`, `/`, `%`...) or begins with a non-letter, AND the literal with those
  characters removed would have matched the full text predicate -- or, for an
  attribute, has a leading non-letter, a brace or a quote that the value class
  refuses, and the rest would have matched;
* `number-with-unit`: a number and a short unit (`+142ms`), which the parser
  counts and which has no word left once the number is removed -- a known
  false positive in the parser, kept rather than special-cased in the detector;
* `no-lowercase-pair`: the regex requires two consecutive lowercase letters;
* `beside-interpolation`: sits next to `{{ }}`. The regex needs `>` before and
  `<` after, so `{{ n }} imports` and `By {{ x }}` are invisible to it -- the
  interpolation-assembled sentences #15665 exists to catch;
* `line-of-multiline-text`: one line of a text node spanning several lines
  (the regex class has no newline, so it never matches such a node);
* `other-attribute-form`: `aria-description`, which the regexes do not list, or
  an attribute written with single quotes.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

from tools.lint._scan_helpers import tracked_paths

_TREES = ("autobot-frontend/src", "autobot-slm-frontend/src")
_SCRIPT = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_TEMPLATE = re.compile(r"<template\b.*</template>", re.DOTALL)
_TEXT = re.compile(r"""> *\s*([A-Za-z][A-Za-z ,.!?'’()-]{2,}?)\s*<""")
_TWO_LOWER = re.compile(r"[a-z]{2}")
_ATTRIBUTE = re.compile(r"""(?<![:@\w-])(?:title|placeholder|aria-label|label|alt)="([A-Za-z][^"{}]{2,})\"""")


def tracked_vue_files(root: Path) -> list[str]:
    """Tracked `.vue` paths in the boundary, from git's index instead of a filesystem walk.

    Through the one shared enumerator (`tracked_paths`, #15926), which scrubs the git
    environment itself. Independence from the primary detector is in the SOURCE (the
    index, not the tree), not in calling git a second way.
    """
    return sorted(p for p in tracked_paths(root, *(f"{tree}/*.vue" for tree in _TREES)) if in_boundary(p))


def in_boundary(rel: str) -> bool:
    """Restated, not imported: a `__tests__/` directory or a stories/spec/test name."""
    name = rel.rsplit("/", 1)[-1]
    if "/__tests__/" in rel:
        return False
    return not any(marker in name for marker in (".stories.", ".spec.", ".test."))


def _region(source: str) -> str:
    match = _TEMPLATE.search(_COMMENT.sub("", _SCRIPT.sub("", source)))
    return match.group(0) if match else ""


def regex_literals(source: str) -> set[tuple[str, str]]:
    """The (kind, literal) pairs the prototype regexes find in one `.vue` source."""
    region = _region(source)
    found = set()
    for raw in _TEXT.findall(region):
        text = html.unescape(raw.strip())
        if len(text) >= 3 and _TWO_LOWER.search(text):
            found.add(("template-text", text))
    found |= {("attribute", html.unescape(t)) for t in _ATTRIBUTE.findall(region)}
    return found


def rederived(root: Path) -> set[tuple[str, str, str]]:
    """(file, kind, literal) over every tracked in-boundary `.vue` file."""
    out: set[tuple[str, str, str]] = set()
    for rel in tracked_vue_files(root):
        source = (root / rel).read_text(encoding="utf-8", errors="replace")
        out |= {(rel, kind, text) for kind, text in regex_literals(source)}
    return out


_CODE_ID = re.compile(r"^([A-Za-z][a-z0-9]*[A-Z]\w*|[A-Za-z]\w*([_-]\w+)+)$")
_TEXT_CLASS = re.compile(r"[A-Za-z][A-Za-z ,.!?'\u2019()-]{2,}")
_TEXT_OUTSIDE = re.compile(r"[^A-Za-z ,.!?'\u2019()-]+")
_ATTR_CLASS = re.compile(r"[A-Za-z][^\"{}]{2,}")
_ATTR_OUTSIDE = re.compile(r"""["{}]+""")
_OPAQUE_ELEMENT = re.compile(r"<(code|pre|svg|path)\b[^>]*>.*?</\1>", re.DOTALL)


def _text_offsets(region: str, literal: str) -> list[int]:
    """Offsets in *region* of every text node the regex reported as *literal*."""
    return [m.start(1) for m in _TEXT.finditer(region) if html.unescape(m.group(1).strip()) == literal]


def _inside_opaque(region: str, offsets: list[int]) -> bool:
    spans = [m.span() for m in _OPAQUE_ELEMENT.finditer(region)]
    return bool(offsets) and all(any(lo <= o < hi for lo, hi in spans) for o in offsets)


def explain_regex_only(source: str, kind: str, literal: str) -> str | None:
    """Why the regexes saw *literal* and the parser, by design, did not; None if unexplained."""
    region = _region(source)
    if kind == "template-text" and _inside_opaque(region, _text_offsets(region, literal)):
        return "opaque-element"
    if len(literal) < 4:
        return "below-minimum"
    if _CODE_ID.match(literal):
        return "identifier-shaped"
    if re.match(r"(https?://|/)", literal):
        return "url-shaped"
    return None


def _beside_interpolation(source: str, literal: str) -> bool:
    """The literal's words appear in the source with at least one `{{ }}` between or beside them."""
    gap = r"(?:\s|\{\{.*?\}\})*"
    pattern = gap.join(re.escape(token) for token in literal.split())
    for match in re.finditer(rf"(?:\{{\{{.*?\}}\}})?{gap}{pattern}{gap}", source, re.DOTALL):
        if "{{" in match.group(0):
            return True
    return False


def _multiline_neighbour(source: str, literal: str) -> bool:
    esc = re.escape(literal)
    return re.search(rf"{esc}[ \t]*\n\s*[^<\s]|[^>\s][ \t]*\n\s*{esc}", source) is not None


def _other_attribute_form(source: str, literal: str) -> bool:
    esc = re.escape(literal)
    pattern = rf"aria-description=[\"']\s*{esc}|\b(?:title|placeholder|alt|label|aria-label)='\s*{esc}"
    return re.search(pattern, source) is not None


def _outside_class(kind: str, literal: str) -> bool:
    """A character the regex class refuses (or a leading non-letter) is present, and the rest would match."""
    if kind == "template-text":
        rest = re.sub(r"^[^A-Za-z]+", "", _TEXT_OUTSIDE.sub("", literal)).strip()
        return rest != literal and bool(_TEXT_CLASS.fullmatch(rest)) and bool(_TWO_LOWER.search(rest))
    rest = _ATTR_OUTSIDE.sub("", re.sub(r"^[^A-Za-z]+", "", literal))
    return rest != literal and bool(_ATTR_CLASS.fullmatch(rest))


_NUMBER_WITH_UNIT = re.compile(r"^[+-]?\d[\d.,]*\s?[A-Za-z]{1,3}$")


def explain_parser_only(source: str, kind: str, literal: str) -> str | None:
    """Why the parser saw *literal* and the regexes, by design, did not; None if unexplained."""
    if kind == "attribute" and _other_attribute_form(source, literal):
        return "other-attribute-form"
    if _outside_class(kind, literal):
        return "outside-regex-class"
    if kind == "attribute":
        return None
    if _NUMBER_WITH_UNIT.match(literal):
        return "number-with-unit"
    if not _TWO_LOWER.search(literal):
        return "no-lowercase-pair"
    if _beside_interpolation(source, literal):
        return "beside-interpolation"
    return "line-of-multiline-text" if _multiline_neighbour(source, literal) else None
