# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One exponential-backoff formula for both frontends (#15402).

Reconnects (WebSocket, live events, terminal) and request retries each
re-derived `base * 2^n` -- 13 copies across the two apps, some capped, two with
jitter added on different sides of the cap. They now call the kit's
`backoffDelay` (`libs/autobot-ui/src/utils/backoff.ts`). This keeps the
formula from being re-derived: a power-of-two expression on a code line of
frontend source outside the kit's own file is a copy.

Only code lines are read (the shared comment stripper), so a doc comment that
explains the doubling is not a copy.
"""

from __future__ import annotations

import functools
import re

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._comment_syntax import code_lines
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_KIT_BACKOFF = "libs/autobot-ui/src/utils/backoff.ts"
_ROOTS = ("libs/autobot-ui", "autobot-frontend/src", "autobot-slm-frontend/src")
_SUFFIXES = (".ts", ".vue", ".js")
#: `Math.pow(2, n)`, `2 ** n`, `1 << n` and `x *= 2` -- every way to double a delay. A shift of
#: anything but 1 is bit packing or hashing (colour channels, string hashes), not a power of two.
_DOUBLING = re.compile(r"Math\.pow\(\s*2\s*,|\b2\s*\*\*\s*[\w(]|\b1\s*<<\s*[\w(]|\*=\s*2\b")


def _doubles(source: str, name: str = "source.ts") -> bool:
    return any(_DOUBLING.search(line.text) for line in code_lines(source, name=name, strip_trailing=True))


def _is_source(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    is_test = "__tests__" in rel or ".test." in name or ".spec." in name or ".stories." in name
    return rel.endswith(_SUFFIXES) and not is_test


def _source_population(root):
    try:
        tracked = tracked_paths(root, *_ROOTS)
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source(rel)]


REACH = declare(
    "backoff-formula-scan",
    discover=_source_population,
    # #18242: population 1132 -> window [982, 1132]; 994 sat in the bottom band, re-pinned mid-window.
    floor=1121,  # mid-window: population 1196, window (1046, 1196)
    what="frontend and kit source",
    roots=_ROOTS,
    growth=150,
)


@functools.lru_cache(maxsize=1)
def _doubling_files() -> tuple[str, ...]:
    root = repo_root()
    return tuple(
        rel for rel in REACH.examined(root) if _doubles((root / rel).read_text(encoding="utf-8", errors="replace"), rel)
    )


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("Math.pow doubling", "const d = base * Math.pow(2, n)\n", True),
        ("exponent operator", "const d = base * 2 ** attempt\n", True),
        ("exponent of a call", "const d = base * 2 ** Math.max(0, n)\n", True),
        ("a helper call", "const d = backoffDelay(n, { base })\n", False),
        ("a comment", "// delay * 2^attempts, Math.pow(2, n)\n", False),
        ("a power-of-two shift", "const d = base * (1 << attempt)\n", True),
        ("colour packing", "return ((r << 16) | (g << 8) | b).toString(16)\n", False),
        ("a string hash", "hash = (hash << 5) - hash + char\n", False),
        ("doubling in place", "delay *= 2\n", True),
        ("other powers", "const area = Math.pow(r, 2)\n", False),
        ("a multiply by 20", "delay *= 20\n", False),
    ],
)
def test_the_matcher_tells_a_doubling_from_anything_else(label: str, source: str, expected: bool) -> None:
    assert _doubles(source) is expected, label


def test_the_scan_sees_the_kit_formula() -> None:
    """The control: the one definition must be found, or the scan is blind."""
    assert _KIT_BACKOFF in _doubling_files()


def test_no_backoff_formula_outside_the_kit() -> None:
    copies = [rel for rel in _doubling_files() if rel != _KIT_BACKOFF]
    assert not copies, (
        f"#15402: {copies} re-derive an exponential backoff; call backoffDelay from '@autobot/ui' "
        "(RETRY_BACKOFF for request retries)."
    )
