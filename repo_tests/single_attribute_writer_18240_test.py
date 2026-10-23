# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One writer each for `data-theme` and `data-ui` on the user frontend (#18240).

`data-theme` had two writers: `composables/useTheme.ts` and a second `applyTheme` in
`stores/useUserStore.ts`, driven by the profile modal's own theme buttons. They disagreed about
which theme was active (the store's default is `light`, the composable's persisted choice may be
`dark`) and whichever ran last won. Refined UI step 2 retired the store's copy and gave the
interface mode (`data-ui`, Minimal / Full) its single owner from the start.

Allowed writers, per attribute:

* `data-theme` -- `composables/useTheme.ts` only.
* `data-ui`    -- `composables/useUiMode.ts`, plus `theme-variant-init.ts`, the pre-mount bootstrap
  that sets the attribute before the bundle mounts so the first paint is not the wrong mode. It
  mirrors the composable's storage key (the same pattern as the theme variant beside it).

A write is `setAttribute` / `removeAttribute` / `toggleAttribute` naming the attribute, or an
assignment to `dataset.theme` / `dataset.ui`. The SLM console is its own application with its own
theming and is out of scope; the embeddable widget sets `data-theme` on its own element, never on
`<html>`, and does so through a config lookup rather than these calls.
"""

from __future__ import annotations

import functools
import re

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._comment_syntax import code_lines
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOT = "autobot-frontend/src"
_SUFFIXES = (".ts", ".vue", ".js")

_ALLOWED = {
    "theme": ("autobot-frontend/src/composables/useTheme.ts",),
    "ui": (
        "autobot-frontend/src/composables/useUiMode.ts",
        "autobot-frontend/src/theme-variant-init.ts",
    ),
}


def _writer_patterns(name: str) -> tuple[re.Pattern[str], ...]:
    attribute = rf"""\(\s*['"`]data-{name}['"`]"""
    return (
        re.compile(rf"\b(?:setAttribute|removeAttribute|toggleAttribute){attribute}"),
        re.compile(rf"\bdataset\.{name}\s*=(?!=)"),
        re.compile(rf"""\bdataset\[\s*['"`]{name}['"`]\s*\]\s*=(?!=)"""),
    )


_PATTERNS = {name: _writer_patterns(name) for name in _ALLOWED}


def _writes(source: str, name: str, path: str = "source.ts") -> bool:
    """True when a code line writes the attribute (a comment or a reader does not)."""
    lines = code_lines(source, name=path, strip_trailing=True)
    return any(pattern.search(line.text) for line in lines for pattern in _PATTERNS[name])


def _is_source(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    is_test = "__tests__" in rel or "/test/" in rel or ".test." in name or ".spec." in name or ".stories." in name
    return rel.endswith(_SUFFIXES) and not is_test


def _source_population(root):
    try:
        tracked = tracked_paths(root, _ROOT)
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source(rel)]


REACH = declare(
    "single-attribute-writer-scan",
    discover=_source_population,
    # Mid-window, from REACH.window(); the arithmetic is on the PR, not here.
    floor=721,
    what="user frontend source",
    roots=(_ROOT,),
    growth=300,
)


@functools.lru_cache(maxsize=1)
def _writers() -> dict[str, tuple[str, ...]]:
    root = repo_root()
    found: dict[str, list[str]] = {name: [] for name in _ALLOWED}
    for rel in REACH.examined(root):
        source = (root / rel).read_text(encoding="utf-8", errors="replace")
        for name in _ALLOWED:
            if _writes(source, name, rel):
                found[name].append(rel)
    return {name: tuple(rels) for name, rels in found.items()}


@pytest.mark.parametrize(
    ("label", "name", "source", "expected"),
    [
        ("setAttribute", "theme", "root.setAttribute('data-theme', t)\n", True),
        ("double quotes", "theme", 'root.setAttribute("data-theme", t)\n', True),
        ("a template literal", "theme", "root.setAttribute(`data-theme`, t)\n", True),
        ("removeAttribute", "theme", "document.documentElement.removeAttribute('data-theme')\n", True),
        ("dataset assignment", "theme", "el.dataset.theme = t\n", True),
        ("dataset bracket", "ui", "el.dataset['ui'] = m\n", True),
        ("ui setAttribute", "ui", "root.setAttribute('data-ui', m)\n", True),
        ("a reader", "theme", "root.getAttribute('data-theme')\n", False),
        ("a dataset read", "theme", "const t = el.dataset.theme\n", False),
        ("a comparison", "theme", "if (el.dataset.theme === 'dark') {}\n", False),
        ("the other attribute", "theme", "root.setAttribute('data-theme-variant', v)\n", False),
        ("a different attribute", "ui", "root.setAttribute('data-ui-density', v)\n", False),
        ("a comment", "theme", "// root.setAttribute('data-theme', t)\n", False),
        ("a jsdoc line", "ui", "/**\n * root.setAttribute('data-ui', m)\n */\n", False),
    ],
)
def test_the_matcher_tells_a_write_from_a_read(label: str, name: str, source: str, expected: bool) -> None:
    assert _writes(source, name) is expected, label


def test_the_scan_sees_every_canonical_writer() -> None:
    """The control: each allowed writer must be found, or the scan is blind to its own subject."""
    found = _writers()
    for name, allowed in _ALLOWED.items():
        missing = [rel for rel in allowed if rel not in found[name]]
        assert not missing, f"the scan did not find the data-{name} writer(s) {missing}; it is not reading them"


@pytest.mark.parametrize("name", sorted(_ALLOWED))
def test_only_the_canonical_writers_write_the_attribute(name: str) -> None:
    extra = [rel for rel in _writers()[name] if rel not in _ALLOWED[name]]
    assert not extra, (
        f"#18240: {extra} write data-{name}. It has one writer ({', '.join(_ALLOWED[name])}); "
        f"call that composable instead of setting the attribute again."
    )
