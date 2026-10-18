# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one detector for user-visible English literals in a `.vue` file (#15665, #12732).

Two guards read the same population: `slm_frontend_bare_ui_literals_test.py`
(#15665, the SLM console, zero baseline) and `hardcoded_ui_literal_ratchet_12732_test.py`
(#12732, both apps, per-file baseline). A second detector for the same question
is a fork, so the parser-based one #15665 wrote lives here and both import it.

WHAT COUNTS AS USER-VISIBLE, and the boundary is the whole design:

- a TEXT NODE inside a template, once tags, `{{ }}` interpolations and
  `{{ $t(...) }}` are removed. Each line of a multi-line text node is judged on
  its own;
- the value of an attribute a user reads -- `placeholder`, `title`, `alt`,
  `aria-label`, `aria-description`, `label`. A static `title="Delete node"` is
  as visible as body text and is the shape that hides from a text-node-only
  scan. Those six are a CLOSED list, not a rule: a literal in a custom
  component's own prop (`message`, `caption`, `hint`, `tooltip`) is user-visible
  and not seen (review finding on #17395);
- (#12732 only) a SCRIPT literal: in `<script>`, a string literal in the
  position `.value = '...'`, `message: '...'`, `title: '...'`, `confirm('...')`,
  `alert('...')` or `Error('...')` that starts with a capital followed by a
  lowercase letter and is at least five characters long. This is a regex over
  the script blocks; it has no second derivation (see the ratchet test).

WHAT DOES NOT COUNT, listed because an unstated exclusion is how a guard ends up
measuring nothing:

- anything under 4 characters, or with no two consecutive letters: `OK`, `%`,
  `·`, `x`, `1.2` are not prose and flagging them teaches people to route
  around the gate;
- a bound attribute (`:title`, `v-bind:title`, `@`, `v-on:`) -- its value is an
  expression, and the expression may well be a `$t(...)` call;
- `<script>`, `<style>`, `<code>`, `<pre>`, `<svg>` and `<path>` contents
  (a file or directory name inside `<code>` is not translatable prose);
- a string that is already an interpolation, a `$t(...)`/`t(...)` call, a URL, a
  path, or a single CamelCase/snake_case identifier.

The template is located after `<script>` and `<style>` blocks are blanked
(newlines kept, so line numbers hold). Otherwise a JSDoc example mentioning
`<template #x>` inside a script starts the greedy template match inside the
script (found by the second derivation, #12732).
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import NamedTuple

#: Attributes a user reads. `aria-*` included: a screen reader is a user.
_VISIBLE_ATTRS = frozenset({"placeholder", "title", "alt", "aria-label", "aria-description", "label"})

#: Elements whose contents are never prose.
_OPAQUE_TAGS = frozenset({"script", "style", "code", "pre", "svg", "path"})

#: Two consecutive LETTERS IN ANY SCRIPT, so `1.2`, `%` and `·` are not prose.
#:
#: `[A-Za-z]{2,}` until #17395: an ASCII-only word test in a guard whose entire
#: purpose is internationalisation. A hardcoded Arabic, Hebrew, Persian or Urdu
#: label contains no ASCII letter, so it scored as "not prose" and the guard
#: passed it -- four of the eleven shipped locales were invisible to the check
#: written to protect them. Measured when it was fixed: the widening surfaced
#: zero new offenders, so nothing had actually slipped through yet. The guard was
#: lucky rather than correct, which is precisely the state a guard must not be
#: left in.
#:
#: `[^\W\d_]` is "word character, not a digit, not an underscore" -- a letter in
#: any script.
_HAS_WORD = re.compile(r"[^\W\d_]{2,}", re.UNICODE)

#: Things that are not text even when they contain words.
_NOT_PROSE = re.compile(r"^(https?://|/|\.{1,2}/|#|\{|\$t\(|t\()")

_MIN_LENGTH = 4

#: "An identifier, not text": CamelCase with an interior capital (`FleetOverview`), or
#: snake/kebab with a separator (`node_id`, `kebab-case-thing`). A plain word such as
#: `Running` or `Close` is prose. The #15665 rule treated every single word as an
#: identifier, so it could not see a one-word label, the commonest literal there is.
#: Narrowing it (#12732) surfaced 181 main-GUI literals and one SLM one
#: (`OrchestrationView.vue`, "services", now a key).
_CODE_IDENTIFIER = re.compile(r"^([A-Za-z][a-z0-9]*[A-Z][A-Za-z0-9]*|[A-Za-z][A-Za-z0-9]*([_-][A-Za-z0-9]+)+)$")


_SCRIPT_BLOCK = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_SCRIPT_BODY = re.compile(r"<script\b[^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE)
_SCRIPT_LITERAL = re.compile(
    r"""(?:\.value\s*=|message:|title:|confirm\(|alert\(|Error\()\s*[`'"]([A-Z][a-z][^`'"]{3,})[`'"]"""
)
KINDS = ("template-text", "attribute", "script")


class Hit(NamedTuple):
    """One literal: where, which kind, the full text, and the display label."""

    line: int
    kind: str
    text: str
    label: str


class _TemplateScan(HTMLParser):
    """Collects user-visible text nodes and attribute values with line numbers."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[Hit] = []
        self._opaque_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # An opaque element's CONTENT is not prose, but attributes are read at
        # any depth: `<pre aria-label="Code block">`, or a `<code aria-label=...>`
        # nested in one, is announced to a screen reader.
        self.handle_startendtag(tag, attrs)
        if tag in _OPAQUE_TAGS:
            self._opaque_depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            # A bound attribute's value is an expression, not a literal.
            if name.startswith((":", "v-bind:", "@", "v-on:")):
                continue
            if name in _VISIBLE_ATTRS and value and _is_prose(value):
                text = value.strip()
                self.found.append(Hit(self.getpos()[0], "attribute", text, f"{name}={text[:60]}"))

    def handle_endtag(self, tag: str) -> None:
        if tag in _OPAQUE_TAGS and self._opaque_depth:
            self._opaque_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._opaque_depth:
            return
        # Drop every interpolation first: `{{ $t('x') }}` and `{{ count }}` are
        # not literals, and a line may mix one with real text.
        text = re.sub(r"\{\{.*?\}\}", " ", data, flags=re.S)
        for chunk in text.splitlines():
            candidate = chunk.strip()
            if _is_prose(candidate):
                self.found.append(Hit(self.getpos()[0], "template-text", candidate, candidate[:60]))


def _is_prose(value: str) -> bool:
    text = value.strip()
    if len(text) < _MIN_LENGTH or not _HAS_WORD.search(text):
        return False
    if _NOT_PROSE.match(text) or _CODE_IDENTIFIER.match(text):
        return False
    return True


def _blank(match: re.Match[str]) -> str:
    """The block with every character but newlines replaced, so line numbers hold."""
    return re.sub(r"[^\n]", " ", match.group(0))


def _template_of(source: str) -> tuple[str, int] | None:
    """The `<template>` body and the line it starts on, or None."""
    cleaned = _SCRIPT_BLOCK.sub(_blank, source)
    match = re.search(r"<template[^>]*>(.*)</template>", cleaned, re.S)
    if not match:
        return None
    return match.group(1), cleaned[: match.start(1)].count("\n")


def template_hits(source: str) -> list[Hit]:
    """Every template-text and attribute literal in one component, line-numbered."""
    template = _template_of(source)
    if template is None:
        return []
    body, offset = template
    scan = _TemplateScan()
    scan.feed(body)
    scan.close()
    return [hit._replace(line=hit.line + offset) for hit in scan.found]


def literals_in_source(source: str, label: str) -> list[str]:
    """Every user-visible bare literal in one component, as `label:line text`."""
    return [f"{label}:{hit.line} {hit.label}" for hit in template_hits(source)]


def script_literals(source: str) -> list[str]:
    """Every script-kind literal, from the `<script>` blocks only."""
    found: list[str] = []
    for block in _SCRIPT_BODY.findall(source):
        found += _SCRIPT_LITERAL.findall(block)
    return found


def literals_in(source: str) -> list[tuple[str, str]]:
    """Every (kind, literal) of all three kinds in one `.vue` source."""
    return [(hit.kind, hit.text) for hit in template_hits(source)] + [
        ("script", text) for text in script_literals(source)
    ]
