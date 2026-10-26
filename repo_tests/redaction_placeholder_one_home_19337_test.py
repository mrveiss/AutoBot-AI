# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A redaction placeholder is spelled in ONE place: ``autobot_shared.secret_redaction`` (#19337).

Two constants live there, distinct on purpose (see the comment above ``LOG_MASK``):
``REDACTED_PLACEHOLDER`` replaces a redacted *value*, ``LOG_MASK`` replaces a secret scrubbed out
of free *text*. Value redactors that wrote ``"<redacted>"`` (CoT events) and ``"***REDACTED***"``
(config revisions, the config cache) now emit ``REDACTED_PLACEHOLDER``; text scrubbers that wrote
``"***"`` (Bedrock error text, workflow output) now use ``LOG_MASK``.

The guard counts every other spelling of a placeholder as a string literal in non-test backend
and shared Python. Six remain, listed on #19337 and held by an exact pin that only goes down: the two partial
key maskers (``abcd...wxyz`` with a short-key fallback; #18221 owns maskers that reveal part of a
secret), a simulated-command stub in the workflow executor, and three display masks equal to
``LOG_MASK`` (the terminal password echo, WhatsApp's ``***NNNN`` phone mask) whose files sit at
their grandfathered size ceilings, so the import waits for those files' splits.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._ratchet_base import base_table
from repo_tests._reach import declare

_ROOTS = ("autobot-backend", "autobot-slm-backend", "autobot_shared")
_HOME = "autobot_shared/secret_redaction.py"
_THIS = "repo_tests/redaction_placeholder_one_home_19337_test.py"
_TEST = re.compile(r"(^|/)(tests?/|test_[^/]*\.py$|[^/]*_test\.py$|conftest\.py$)")
_SPELLINGS = frozenset(
    {"***", "****", "**********", "<redacted>", "<REDACTED>", "***REDACTED***", "[redacted]", "[REDACTED]"}
)

#: Placeholder literals still outside the home (measured at #19337; listed on the issue). Down-only.
PIN = {"placeholder_literals": 6}


def _modules(root: Path) -> list[Path]:
    found = []
    for top in _ROOTS:
        base = root / top
        if base.is_dir():
            found += [p for p in sorted(base.rglob("*.py")) if not _TEST.search(p.relative_to(root).as_posix())]
    return found


REACH = declare(
    "redaction-placeholder-literals",
    discover=_modules,
    floor=3143,  # mid-window: population 3293, window (2993, 3293)
    growth=300,  # ~9%: ordinary growth between repins must not turn an unrelated PR red
    what="non-test Python modules",
    roots=_ROOTS,
)


def placeholder_literals(source: str, rel: str) -> list[str]:
    """Each placeholder spelled as a string literal in *source* (docstrings are prose and not read)."""
    if rel == _HOME:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    docstrings = {
        id(n.body[0].value)
        for n in ast.walk(tree)
        if isinstance(n, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and n.body
        and isinstance(n.body[0], ast.Expr)
        and isinstance(n.body[0].value, ast.Constant)
    }
    return [
        f"{rel}:{n.lineno}: {n.value!r}"
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and n.value in _SPELLINGS and id(n) not in docstrings
    ]


def _live(root: Path) -> list[str]:
    files = REACH.examined(root)
    found = [
        h for p in files for h in placeholder_literals(p.read_text(encoding="utf-8"), p.relative_to(root).as_posix())
    ]
    REACH.completed(files)
    return found


def test_no_new_placeholder_spelling() -> None:
    found = _live(repo_root())
    pinned = PIN["placeholder_literals"]
    assert len(found) <= pinned, f"use REDACTED_PLACEHOLDER / LOG_MASK from {_HOME} (#19337): {found}"
    assert len(found) == pinned, f"{len(found)} placeholder literals, pin says {pinned}: lower PIN in this PR"


def test_the_pin_was_not_raised_against_the_base() -> None:
    base = base_table(repo_root(), (_THIS,), "PIN")
    if base:
        assert PIN["placeholder_literals"] <= base["placeholder_literals"], "the pin only goes down (#19337)"


@pytest.mark.parametrize("source", ['_REDACTED = "<redacted>"\n', 'obj[k] = "***REDACTED***"\n', 'MASK = "***"\n'])
def test_each_spelling_is_flagged(source: str) -> None:
    assert placeholder_literals(source, "x.py")


def test_the_home_a_docstring_and_other_strings_are_not_flagged() -> None:
    assert not placeholder_literals('LOG_MASK = "***"\n', _HOME)
    assert not placeholder_literals('def f():\n    """***"""\n    return "*** bold ***"\n', "x.py")
