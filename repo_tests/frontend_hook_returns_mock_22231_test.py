# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A Vitest hook arrow must not return a mock (#22231).

Vitest runs a function returned from ``beforeEach``/``beforeAll`` as that hook's teardown.
``beforeEach(() => get.mockReset())`` returns the mock (``mockReset`` returns it), so Vitest calls the
mock again after each test and a rejecting or throwing mock is reported as the test's own failure.
The fix shape is a block body that returns nothing: ``beforeEach(() => { get.mockReset() })``.

The detector flags an expression-bodied arrow (no ``{``) passed to any of the four hooks whose body
calls a ``.mock*(...)`` method. All four hooks are checked, although only the two ``before`` hooks treat
the return value as teardown, so the form is uniform. Scope: every test or spec file under both
frontends' ``src``. The reach floor stops an empty glob from reading as a clean 0.

The guard has no allowlist: a file that still has the shape fails it until fixed.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

_ROOTS = ("autobot-frontend/src", "autobot-slm-frontend/src")
_TEST_FILE = re.compile(r"\.(?:test|spec)\.(?:ts|tsx|js)$")
_HOOK_ARROW_RETURNS_MOCK = re.compile(
    r"\b(?:beforeEach|beforeAll|afterEach|afterAll)\(\s*(?:async\s*)?\(\)\s*=>\s*(?!\{)[^{};\n]*\.mock[A-Z]\w*\("
)
_FLOOR = 500


def offending(text: str) -> int:
    """Count hook arrows in *text* whose expression body calls a mock method."""
    return len(_HOOK_ARROW_RETURNS_MOCK.findall(text))


def _population(root: Path) -> list[str]:
    return [
        p.relative_to(root).as_posix()
        for rel in _ROOTS
        for p in sorted((root / rel).rglob("*"))
        if _TEST_FILE.search(p.name) and "node_modules" not in p.parts
    ]


REACH = declare(
    "frontend-hook-returns-mock-scan",
    discover=_population,
    floor=_FLOOR,
    growth=500,
    what="test and spec files in both frontends",
    roots=_ROOTS,
)


class TestTheDetectorWorksBeforeItsOutputIsRead:
    def test_the_arrow_form_fails(self) -> None:  # positive control
        assert offending("beforeEach(() => get.mockReset())") == 1
        assert offending("  beforeAll(() => vi.fn().mockClear())") == 1
        assert offending("afterEach(() => m.mockImplementation(() => 1))") == 1
        assert offending("beforeEach(\n  () =>\n    get.mockRestore()\n)") == 1

    def test_the_block_form_passes(self) -> None:  # negative control, the contrast pair
        assert offending("beforeEach(() => { get.mockReset() })") == 0
        assert offending("beforeEach(() => {\n  get.mockReset()\n})") == 0
        assert offending("beforeEach(() => vi.useFakeTimers())") == 0
        assert offending("it('x', () => get.mockReset())") == 0


def test_no_hook_arrow_returns_a_mock() -> None:
    root = repo_root()
    for rel in _ROOTS:
        assert (root / rel).is_dir(), f"{rel} has moved; this guard reads it by path"
    paths = REACH.examined(root)
    assert len(paths) >= _FLOOR, f"only {len(paths)} test files reached; floor is {_FLOOR}"
    bad = {p: n for p in paths if (n := offending((root / p).read_text(encoding="utf-8")))}
    assert not bad, (
        f"hook arrows returning a mock (Vitest runs the return value as teardown, #22231): {bad}. "
        "Use a block body: beforeEach(() => { mock.mockReset() })."
    )
