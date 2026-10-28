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
and shared Python. Six remain, listed on #19337 and held by an exact per-file pin that only goes
down (a swap, one literal removed and another added elsewhere, fails as a new site plus a stale
entry; #19698): the two partial
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
from repo_tests._ratchet_base import base_table, base_tree_texts
from repo_tests._reach import declare

_ROOTS = ("autobot-backend", "autobot-slm-backend", "autobot_shared")
_HOME = "autobot_shared/secret_redaction.py"
_THIS = "repo_tests/redaction_placeholder_one_home_19337_test.py"
_TEST = re.compile(r"(^|/)(tests?/|test_[^/]*\.py$|[^/]*_test\.py$|conftest\.py$)")
_SPELLINGS = frozenset(
    {"***", "****", "**********", "<redacted>", "<REDACTED>", "***REDACTED***", "[redacted]", "[REDACTED]"}
)

#: Placeholder literals still outside the home, per file (measured at #19337, per-file since #19698). Down-only.
PIN: dict[str, int] = {
    "autobot-backend/api/terminal.py": 1,
    "autobot-backend/api/user_provider_credentials.py": 1,
    "autobot-backend/integrations/whatsapp_integration.py": 2,
    "autobot-backend/services/workflow_automation/executor.py": 1,
    "autobot-backend/slash_command_handler.py": 1,
}


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


def base_per_file(root: Path) -> dict[str, int]:
    """Per-file literal counts in the BASE tree, same scope as :func:`_live`, for a legacy total pin."""
    found = []
    for top in _ROOTS:
        for path, text in base_tree_texts(root, top).items():
            if path.endswith(".py") and not _TEST.search(path):
                found += placeholder_literals(text, path)
    return per_file(found)


def per_file(found: list[str]) -> dict[str, int]:
    """Count hits (``path:line: literal``) per path."""
    counts: dict[str, int] = {}
    for hit in found:
        path = hit.split(":", 1)[0]
        counts[path] = counts.get(path, 0) + 1
    return counts


def compare_to_pin(now: dict[str, int], pinned: dict[str, int]) -> tuple[dict[str, tuple[int, int]], list[str]]:
    """(new or raised sites, stale or lowered entries) of *now* against *pinned*."""
    new = {k: (pinned.get(k, 0), v) for k, v in now.items() if v > pinned.get(k, 0)}
    stale = [f"{k}: pin {v}, now {now.get(k, 0)}" for k, v in pinned.items() if now.get(k, 0) < v]
    return new, stale


def test_no_new_placeholder_spelling() -> None:
    found = _live(repo_root())
    new, stale = compare_to_pin(per_file(found), PIN)
    assert not new, (
        f"NEW placeholder literals (path: (pinned, now)): {new}; "
        f"use REDACTED_PLACEHOLDER / LOG_MASK from {_HOME} (#19337): {found}"
    )
    assert not stale, f"STALE pin entries: {stale}; lower or delete them in this PR (#19337)"


def test_the_pin_was_not_raised_against_the_base() -> None:
    base = base_table(repo_root(), (_THIS,), "PIN")
    if "placeholder_literals" in base:  # the base pinned a bare total (before #19698): measure its tree
        assert sum(PIN.values()) <= base["placeholder_literals"], "the pin only goes down (#19337)"
        base = base_per_file(repo_root())
    new, _ = compare_to_pin(PIN, base)
    assert (
        not new
    ), f"PIN rose or gained entries against the base (path: (base, now)): {new}; it only goes down (#19337)"


def test_a_swap_fails_as_one_new_site_and_one_stale_entry() -> None:
    pinned = {"a.py": 1, "b.py": 1}
    new, stale = compare_to_pin({"b.py": 1, "c.py": 1}, pinned)  # a.py cleared, c.py gained one: same total
    assert new == {"c.py": (0, 1)}
    assert stale == ["a.py: pin 1, now 0"]


def test_per_file_counts_group_hits_by_path() -> None:
    assert per_file(["x/a.py:3: '***'", "x/a.py:9: '***'", "y.py:1: '<redacted>'"]) == {"x/a.py": 2, "y.py": 1}


@pytest.mark.parametrize("source", ['_REDACTED = "<redacted>"\n', 'obj[k] = "***REDACTED***"\n', 'MASK = "***"\n'])
def test_each_spelling_is_flagged(source: str) -> None:
    assert placeholder_literals(source, "x.py")


def test_the_home_a_docstring_and_other_strings_are_not_flagged() -> None:
    assert not placeholder_literals('LOG_MASK = "***"\n', _HOME)
    assert not placeholder_literals('def f():\n    """***"""\n    return "*** bold ***"\n', "x.py")
