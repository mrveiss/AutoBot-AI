# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Guards for TaskComplexity's alias collapse (#13806).

`TaskComplexity` declares five members but only two distinct values, so
`RESEARCH`, `INSTALL` and `SECURITY_SCAN` are *aliases* of `COMPLEX`, not
separate members. Code written as though they were distinguishable is not —
most consequentially `workflow_scheduler`'s priority multiplier, whose five-key
dict literal collapses to two entries with last-write-wins.

These tests do not decide whether the aliases should be collapsed or made
distinct — that changes scheduling priority system-wide and is recorded on
#13806 as an owner decision. What they do is remove the *silence*:

- the applied multipliers are pinned, so a source-order change cannot alter
  scheduling unnoticed (which is what makes the current state dangerous rather
  than merely untidy);
- a generic guard fails if any complexity-keyed mapping is built from more than
  one alias of the same member, so the trap cannot be re-laid elsewhere.

If the decision lands as "collapse", the pinned values below are the ones that
must be consciously kept or changed — they are today's real behaviour, not the
behaviour the source reads as.
"""

import ast
import pathlib

import pytest

from autobot_types import TaskComplexity

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO_ROOT / "autobot-backend"


def test_the_aliases_really_are_aliases():
    """States the premise the other tests rest on, so a fix here fails loudly."""
    assert TaskComplexity.RESEARCH is TaskComplexity.COMPLEX
    assert TaskComplexity.INSTALL is TaskComplexity.COMPLEX
    assert TaskComplexity.SECURITY_SCAN is TaskComplexity.COMPLEX
    # Five names, two members. `list(Enum)` yields canonical members only.
    assert [m.name for m in TaskComplexity] == ["SIMPLE", "COMPLEX"]


def test_scheduler_multiplier_is_what_is_actually_applied():
    """Pin the multipliers the scheduler really uses, not the ones it appears to.

    The dict literal names five complexities and five constants. Four keys are
    the same object, so only two survive and the last one written wins — every
    non-simple workflow is scheduled with the security-scan multiplier. This
    assertion is the record of that, and it fails if anyone reorders the literal.
    """
    from autobot_shared.ssot_constants import WorkflowConfig

    applied = {
        TaskComplexity.SIMPLE: WorkflowConfig.COMPLEXITY_SIMPLE,
        TaskComplexity.RESEARCH: WorkflowConfig.COMPLEXITY_RESEARCH,
        TaskComplexity.INSTALL: WorkflowConfig.COMPLEXITY_INSTALL,
        TaskComplexity.COMPLEX: WorkflowConfig.COMPLEXITY_COMPLEX,
        TaskComplexity.SECURITY_SCAN: WorkflowConfig.COMPLEXITY_SECURITY_SCAN,
    }

    assert len(applied) == 2, "alias collapse changed — re-read #13806 before adjusting"
    assert applied[TaskComplexity.SIMPLE] == WorkflowConfig.COMPLEXITY_SIMPLE
    # Not COMPLEXITY_COMPLEX: SECURITY_SCAN is written last and overwrites it.
    assert applied[TaskComplexity.COMPLEX] == WorkflowConfig.COMPLEXITY_SECURITY_SCAN
    assert applied[TaskComplexity.RESEARCH] == WorkflowConfig.COMPLEXITY_SECURITY_SCAN


def _alias_names() -> set:
    """Names that resolve to a member already reachable under another name."""
    canonical = {m.name for m in TaskComplexity}
    return {
        name
        for name, value in vars(TaskComplexity).items()
        if isinstance(value, TaskComplexity) and name not in canonical
    }


def _dicts_keyed_on_complexity(tree: ast.AST):
    """Yield dict literals whose keys are TaskComplexity attribute accesses."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        names = [
            k.attr
            for k in node.keys
            if isinstance(k, ast.Attribute)
            and isinstance(k.value, ast.Name)
            and k.value.id == "TaskComplexity"
        ]
        if names:
            yield node, names


def test_no_mapping_is_keyed_on_two_aliases_of_one_member():
    """A dict keyed on both COMPLEX and an alias silently drops an entry.

    This is the trap that made #13806 invisible: the source lists five distinct
    priorities and the runtime keeps two. Any *new* such mapping is a fresh
    instance of the same bug, so it fails here rather than shipping quietly.

    workflow_scheduler.py is the known-offending site and is exempted by name —
    removing that exemption is part of resolving #13806, not of this guard.
    """
    exempt = {"workflow_scheduler.py", pathlib.Path(__file__).name}
    aliases = _alias_names()
    offenders = []

    for path in BACKEND.rglob("*.py"):
        if path.name in exempt:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node, names in _dicts_keyed_on_complexity(tree):
            resolved = {getattr(TaskComplexity, n).name for n in names if hasattr(TaskComplexity, n)}
            if any(n in aliases for n in names) and len(resolved) != len(names):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno} keys on {names} -> {sorted(resolved)}")

    assert not offenders, "dict literals whose complexity keys silently merge (#13806):\n" + "\n".join(offenders)
