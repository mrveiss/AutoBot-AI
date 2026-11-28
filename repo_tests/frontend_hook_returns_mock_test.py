# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A Vitest hook arrow must not return a mock (#22231).

Vitest runs a function returned from ``beforeEach``/``beforeAll`` as that hook's teardown.
``beforeEach(() => get.mockReset())`` returns the mock (``mockReset`` returns it), so Vitest calls the
mock again after each test and a rejecting or throwing mock is reported as the test's own failure.
The fix shape is a block body that returns nothing: ``beforeEach(() => { get.mockReset() })``.

The detector reads each hook call's first argument up to its closing paren (so a body may span lines and
hold nested blocks) and flags an expression-bodied arrow whose body, outside any nested ``{...}``, calls a
``.mock*(...)`` method, or a bare ``x.mockReset``/``mockClear``/``mockRestore`` reference. All four hooks are checked, although only the two ``before`` hooks treat
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
_HOOK_CALL = re.compile(r"\b(?:beforeEach|beforeAll|afterEach|afterAll)\(\s*")
_EXPRESSION_ARROW = re.compile(r"(?:async\s*)?\(\)\s*=>\s*(?!\{)")
_MOCK_CALL = re.compile(r"\.mock[A-Z]\w*\(")
_BARE_MOCK_REFERENCE = re.compile(r"[\w.$]+\.mock(?:Reset|Clear|Restore)\s*")
_FLOOR = 830
_PAIRS = {"(": ")", "{": "}"}


def _argument(text: str, start: int) -> str:
    """The hook's first argument: from *start* to the call's closing paren, nesting-aware."""
    depth = 1
    for i in range(start, len(text)):
        if text[i] in "({[":
            depth += 1
        elif text[i] in ")}]":
            depth -= 1
            if depth == 0:
                return text[start:i]
    return text[start:]


def _without_blocks(body: str) -> str:
    """*body* with every balanced ``{...}`` emptied, so a nested block's own calls do not count."""
    out, depth = [], 0
    for ch in body:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(depth - 1, 0)
        elif depth == 0:
            out.append(ch)
    return "".join(out)


def _returns_mock(argument: str) -> bool:
    arrow = _EXPRESSION_ARROW.match(argument)
    if arrow:
        return bool(_MOCK_CALL.search(_without_blocks(argument[arrow.end() :])))
    return bool(_BARE_MOCK_REFERENCE.fullmatch(argument))


def offending(text: str) -> int:
    """Count hooks whose expression-bodied arrow, or bare mock method, returns a mock."""
    return sum(_returns_mock(_argument(text, m.end())) for m in _HOOK_CALL.finditer(text))


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
    growth=40,
    what="test and spec files in both frontends",
    roots=_ROOTS,
)


class TestTheDetectorWorksBeforeItsOutputIsRead:
    def test_the_arrow_form_fails(self) -> None:  # positive control
        assert offending("beforeEach(() => get.mockReset())") == 1
        assert offending("  beforeAll(() => vi.fn().mockClear())") == 1
        assert offending("afterEach(() => m.mockImplementation(() => 1))") == 1
        assert offending("beforeEach(\n  () =>\n    get.mockRestore()\n)") == 1
        assert offending("beforeEach(() =>\n  x\n    .mockReset()\n)") == 1  # multi-line chain
        assert offending("beforeEach(() => vi.fn(() => {}).mockReset())") == 1  # nested block arrow
        assert offending("beforeEach(mock.mockReset)") == 1  # bare mock reference
        assert offending("afterAll(x.mockClear )") == 1

    def test_the_block_form_passes(self) -> None:  # negative control, the contrast pair
        assert offending("beforeEach(() => { get.mockReset() })") == 0
        assert offending("beforeEach(() => {\n  get.mockReset()\n})") == 0
        assert offending("beforeEach(() => vi.useFakeTimers())") == 0
        assert offending("it('x', () => get.mockReset())") == 0
        assert offending("beforeEach(() => {\n  x\n    .mockReset()\n})") == 0  # chain, block form
        assert offending("beforeEach(() => { vi.fn(() => {}).mockReset() })") == 0  # nested, block form
        assert offending("beforeEach(() => { mock.mockReset() })") == 0  # bare reference, block form
        assert offending("beforeEach(resetApi)") == 0  # bare non-mock function
        assert offending("beforeEach(() => wrap(() => { m.mockReset() }))") == 0  # mock only inside a block


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
