# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No NEW user-visible literal in the SLM console (#15665, #14781).

`autobot-slm-frontend` has never had an i18n gate. #15665 found the log
viewer's "No logs available" written as a bare English string and said so in its
title: *"no i18n gate covers this app"*. Fixing that one literal without a gate
leaves the next one to land unnoticed, which is why the two issues are one.

`check:i18n` (already wired in this app's `package.json`, pointing at the shared
`check-i18n-keys.mjs`) answers the OPPOSITE question: it fails when code uses a
key that `en.json` lacks. It cannot see a string that never became a key. This
guard is that direction.

WHAT COUNTS AS USER-VISIBLE, and the boundary is the whole design:

- a TEXT NODE inside a template, once tags, `{{ }}` interpolations and
  `{{ $t(...) }}` are removed;
- the value of an attribute a user reads -- `placeholder`, `title`, `alt`,
  `aria-label`, `aria-description`, `label`. A static `title="Delete node"` is
  as visible as body text and is the shape that hides from a text-node-only
  scan.

  Those six are a CLOSED list, not a rule, and that is the guard's main blind
  spot (review finding on #17395). A literal in a custom component's own prop --
  `<StatusCard message="Node is unreachable" />`, or `caption`, `hint`, `tooltip`
  -- is user-visible and this guard does not look at it. There are none today:
  every non-listed attribute carrying prose in the app right now is a Vue
  `<transition>` CSS class (`enter-active-class` and friends), checked with a
  scanner built for that question rather than assumed. Adding a name here is the
  fix when one appears; the zero baseline below is zero for the shapes named
  above, not for every readable attribute.

WHAT DOES NOT COUNT, listed because an unstated exclusion is how a guard ends up
measuring nothing:

- anything under 4 characters, or with no two consecutive letters: `OK`, `%`,
  `·`, `x`, `1.2` are not prose and flagging them teaches people to route
  around the gate;
- a bound attribute (`:title`, `v-bind:title`) -- its value is an expression,
  and the expression may well be a `$t(...)` call;
- `<script>`, `<style>`, `<code>` and `<pre>` contents;
- a string that is already an interpolation, a `$t(...)`/`t(...)` call, a URL, a
  path, or a single CamelCase/snake_case identifier.

WHERE THIS RUNS, because a gate that does not fire on the change it guards is
the shape #15665 is about. It declares a `*.vue` glob, and the python path
filter does not cover `autobot-slm-frontend/` -- a gap recorded deliberately in
`glob_declared_reads_15900_test.py`, since widening the filter to those trees
would cost twelve shards on nearly every pull request. So a .vue-only change
would not reach the python suite at all. `slm-frontend-check.yml`, which DOES
trigger on `autobot-slm-frontend/**`, runs this file directly for exactly that
reason. Two entry points, one guard, and the recorded glob dependency is what
makes the arrangement legible rather than lucky.

THERE IS NO BASELINE, and that is a measurement rather than an aspiration. The
sweep #15665 asked for found FIVE user-visible literals across 113 components:
one real `aria-label` (`App.vue`) and four sentences assembled around
interpolations -- `By {{ x }} at {{ y }}`, `{{ n }} (DB {{ d }})`,
`({{ ms }}ms)`, `{{ type }} - ID: {{ id }}` -- each of which reads as English
word order in every locale. All five are fixed in the same change, so this guard
starts at zero and an exemption list would be an empty mechanism inviting its
first entry.

The app is otherwise thoroughly internationalised: 3,185 keys for 113
components. Five is the honest number, and it is small because the work was
almost entirely already done -- not because the scan is blind. The fixtures at
the bottom are what distinguish those two.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

_SRC = Path("autobot-slm-frontend") / "src"

#: Attributes a user reads. `aria-*` included: a screen reader is a user.
_VISIBLE_ATTRS = frozenset({"placeholder", "title", "alt", "aria-label", "aria-description", "label"})

#: Elements whose contents are never prose.
_OPAQUE_TAGS = frozenset({"script", "style", "code", "pre", "svg", "path"})

#: Two consecutive letters, so `1.2`, `%` and `·` are not prose.
_HAS_WORD = re.compile(r"[A-Za-z]{2,}")

#: A single identifier -- `FleetOverview`, `node_id`, `kebab-case-thing`.
_IDENTIFIER_ONLY = re.compile(r"^[A-Za-z][A-Za-z0-9]*([_-][A-Za-z0-9]+)*$")

#: Things that are not text even when they contain words.
_NOT_PROSE = re.compile(r"^(https?://|/|\.{1,2}/|#|\{|\$t\(|t\()")

_MIN_LENGTH = 4


class _TemplateScan(HTMLParser):
    """Collects user-visible text nodes and attribute values with line numbers."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[tuple[int, str]] = []
        self._opaque_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _OPAQUE_TAGS:
            self._opaque_depth += 1
            return
        if self._opaque_depth:
            return
        for name, value in attrs:
            # A bound attribute's value is an expression, not a literal.
            if name.startswith((":", "v-bind:", "@", "v-on:")):
                continue
            if name in _VISIBLE_ATTRS and value and _is_prose(value):
                self.found.append((self.getpos()[0], f"{name}={value.strip()[:60]}"))

    def handle_endtag(self, tag: str) -> None:
        if tag in _OPAQUE_TAGS and self._opaque_depth:
            self._opaque_depth -= 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in _OPAQUE_TAGS:
            self.handle_starttag(tag, attrs)

    def handle_data(self, data: str) -> None:
        if self._opaque_depth:
            return
        # Drop every interpolation first: `{{ $t('x') }}` and `{{ count }}` are
        # not literals, and a line may mix one with real text.
        text = re.sub(r"\{\{.*?\}\}", " ", data, flags=re.S)
        for chunk in text.splitlines():
            candidate = chunk.strip()
            if _is_prose(candidate):
                self.found.append((self.getpos()[0], candidate[:60]))


def _is_prose(value: str) -> bool:
    text = value.strip()
    if len(text) < _MIN_LENGTH or not _HAS_WORD.search(text):
        return False
    if _NOT_PROSE.match(text) or _IDENTIFIER_ONLY.match(text):
        return False
    return True


def _template_of(source: str) -> tuple[str, int] | None:
    """The `<template>` body and the line it starts on, or None."""
    match = re.search(r"<template[^>]*>(.*)</template>", source, re.S)
    if not match:
        return None
    return match.group(1), source[: match.start(1)].count("\n")


def literals_in_source(source: str, label: str) -> list[str]:
    """Every user-visible bare literal in one component, as `label:line text`."""
    template = _template_of(source)
    if template is None:
        return []
    body, offset = template
    scan = _TemplateScan()
    scan.feed(body)
    scan.close()
    return [f"{label}:{line + offset} {text}" for line, text in scan.found]


def _scan() -> tuple[list[str], int]:
    """(offenders, components scanned)."""
    root = repo_root() / _SRC
    offenders: list[str] = []
    scanned = 0
    for path in sorted(root.rglob("*.vue")):
        scanned += 1
        offenders.extend(literals_in_source(path.read_text(encoding="utf-8"), path.relative_to(root).as_posix()))
    return offenders, scanned


#: A floor, not a census: if the walk stops finding components, every assertion
#: below would pass by matching nothing.
_MIN_COMPONENTS_SEEN = 100


def test_the_scan_reaches_the_components_it_guards() -> None:
    """A walk that matches nothing would make the assertion below vacuous."""
    _, scanned = _scan()

    assert scanned >= _MIN_COMPONENTS_SEEN, (
        f"only {scanned} component(s) found under {_SRC.as_posix()}, expected at least "
        f"{_MIN_COMPONENTS_SEEN} -- this guard has stopped reaching its subject, so a pass "
        "means nothing was looked at rather than nothing was wrong"
    )


def test_no_user_visible_literal_remains() -> None:
    """#15665: every user-visible string goes through `$t(...)`."""
    offenders, _ = _scan()

    assert not offenders, (
        "user-visible text in the SLM console that is not translated:\n  "
        + "\n  ".join(offenders)
        + "\n\nRender it through `$t('key')` and add the key to "
        "autobot-slm-frontend/src/locales/en.json, then run "
        "`scripts/lift_locale_translations.py --app autobot-slm-frontend/src/locales` so every "
        "locale keeps the key. A sentence assembled around interpolations needs ONE key with "
        "parameters -- `$t('x', { a, b })` -- because word order differs by language."
    )


# --- Fixtures -----------------------------------------------------------------
#
# The tree is clean, so every assertion above reports a true negative either way
# -- which is exactly how a scanner that cannot scan looks correct. These feed it
# each shape it claims to catch, and each shape it claims to ignore.

_CAUGHT = {
    "text node": "<template><div>No logs available</div></template>",
    "placeholder": '<template><input placeholder="Enter a hostname" /></template>',
    "title attribute": '<template><button title="Delete this node">x</button></template>',
    "aria-label": '<template><nav aria-label="Main content">x</nav></template>',
    "nested deeply": "<template><div><section><p>Something went wrong</p></section></div></template>",
    "multiline tag": '<template>\n<button\n  class="x"\n  title="Retry the deploy"\n>ok</button>\n</template>',
    "text beside an interpolation": "<template><p>Resolved by {{ user }} yesterday</p></template>",
}

_IGNORED = {
    "a translated string": "<template><div>{{ $t('a.b') }}</div></template>",
    "a bound attribute": "<template><input :placeholder=\"$t('a.b')\" /></template>",
    "a short token": "<template><span>OK</span></template>",
    "an identifier": "<template><span>FleetOverview</span></template>",
    "a number": "<template><span>1.25</span></template>",
    "script contents": "<template><div>{{ x }}</div></template><script>const s = 'Delete this node'</script>",
}


@pytest.mark.parametrize("shape", sorted(_CAUGHT))
def test_the_detector_catches_each_shape_it_claims_to(shape: str) -> None:
    assert literals_in_source(_CAUGHT[shape], "fixture.vue"), (
        f"a {shape} is user-visible text and must be caught; a detector validated only on "
        "inputs it handles cannot report its own blind spot"
    )


@pytest.mark.parametrize("shape", sorted(_IGNORED))
def test_the_detector_ignores_each_shape_it_claims_to(shape: str) -> None:
    assert (
        literals_in_source(_IGNORED[shape], "fixture.vue") == []
    ), f"{shape} is not a bare literal; flagging it teaches people to route around the gate"


def test_a_component_without_a_template_is_not_an_error() -> None:
    """A `.vue` file that is script-only must read as clean, not as unscannable."""
    assert literals_in_source("<script setup lang=\"ts\">const a = 'Delete'</script>", "fixture.vue") == []
