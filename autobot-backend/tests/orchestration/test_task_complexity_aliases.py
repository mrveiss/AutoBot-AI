# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""TaskComplexity has no alias members, and no mapping can hide one (#13806).

`TaskComplexity` used to declare five names for two members: `RESEARCH`,
`INSTALL` and `SECURITY_SCAN` all carried the value `"complex"`, which makes
them Enum *aliases* of `COMPLEX` rather than separate members. Code written as
though they were distinguishable was not -- most consequentially
`workflow_scheduler._calculate_priority_score`, whose five-key multiplier dict
collapsed to two entries with last-write-wins, so every non-simple workflow ran
at `COMPLEXITY_SECURITY_SCAN` and the #376 tuning never applied.

The direction was an owner decision, taken on #13806 (2026-09-06): collapse,
because nothing in the tree ever distinguished the three and the thing they
stood in for -- *what kind of workflow is this* -- is carried by
`TemplateCategory`, whose members do not collide. These tests hold that:

* no two names in the enum resolve to one member, so re-laying the trap fails
  here first rather than silently retuning the scheduler;
* the multipliers actually applied are pinned, including the deliberate choice
  to keep `COMPLEX` at the 1.3 that really ran rather than the 1.2 the source
  used to claim;
* a repo-wide AST sweep fails on any dict literal whose complexity keys merge.
  `workflow_scheduler.py` is **no longer exempt** -- removing that exemption was
  part of resolving #13806.

The sweep parses. A `grep` for `TaskComplexity.RESEARCH` is satisfied by this
very docstring, and by the migration comments left at the template call sites;
`test_the_detector_ignores_the_name_in_prose` is the control that proves the
difference, and `test_the_detector_finds_a_planted_collapse` is the control that
proves it can see anything at all.
"""

import ast
import enum
import math
import pathlib

from autobot_types import TaskComplexity

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO_ROOT / "autobot-backend"

#: An enum carrying the exact defect, used only to exercise the detector.
#: Written here rather than discovered in the tree, because the tree is
#: supposed to be clean -- a detector whose only population is empty reports
#: "nothing found" and "did not look" identically (MEASUREMENT_DISCIPLINE.md).


class _AliasedForControl(enum.Enum):
    SIMPLE = "simple"
    COMPLEX = "complex"
    RESEARCH = "complex"  # alias of COMPLEX, exactly as #13806 described


def test_task_complexity_has_no_alias_members():
    """Every name is its own member. Re-adding a duplicate value fails here.

    `__members__` maps *names* (aliases included) to members; iterating the
    enum yields canonical members only. Equal lengths is the whole claim, and
    it is the one assertion that distinguishes the three retired names from
    each other: if any of them comes back carrying `"complex"`, the name count
    rises while the member count does not.
    """
    names = list(TaskComplexity.__members__)
    members = list(TaskComplexity)

    assert names == [m.name for m in members], (
        "TaskComplexity has alias names that resolve to an already-reachable "
        f"member -- the #13806 collapse is back. names={names} "
        f"members={[m.name for m in members]}"
    )
    assert [m.name for m in members] == ["SIMPLE", "COMPLEX"]
    assert len({m.value for m in members}) == len(members)

    # The three retired names, asserted individually: a reader checking whether
    # this guard covers *their* name finds it by name, and a partial revival of
    # one of the three fails on its own line.
    for retired in ("RESEARCH", "INSTALL", "SECURITY_SCAN"):
        assert not hasattr(TaskComplexity, retired), (
            f"TaskComplexity.{retired} is back. It was an alias of COMPLEX "
            "(#13806); if a genuinely distinct complexity class is wanted it "
            "needs a distinct value and a scheduler multiplier of its own."
        )


def test_scheduler_multiplier_has_one_entry_per_complexity():
    """What the scheduler writes is what the scheduler applies.

    The literal in `workflow_scheduler._calculate_priority_score` is rebuilt
    here from the same constants. Before #13806 it named five complexities and
    kept two; the assertion that `len(applied) == len(list(TaskComplexity))` is
    what makes a future collapse loud instead of a silent retune.
    """
    from autobot_shared.ssot_constants import WorkflowConfig

    applied = {
        TaskComplexity.SIMPLE: WorkflowConfig.COMPLEXITY_SIMPLE,
        TaskComplexity.COMPLEX: WorkflowConfig.COMPLEXITY_COMPLEX,
    }

    assert len(applied) == len(
        list(TaskComplexity)
    ), "a complexity-keyed mapping lost an entry -- see #13806 before adjusting"
    assert applied[TaskComplexity.SIMPLE] == 0.8
    # 1.3, not the 1.2 the source used to read as. COMPLEXITY_SECURITY_SCAN was
    # written last into the old five-key literal and overwrote COMPLEXITY_COMPLEX,
    # so 1.3 is what every non-simple workflow has always been scheduled at.
    # Collapsing the aliases was held to zero behaviour change, which means this
    # number: re-tuning it is a scheduling decision and is not this issue.
    assert applied[TaskComplexity.COMPLEX] == 1.3

    # AND THE SCHEDULER MUST ACTUALLY APPLY THEM (CodeRabbit, #13806). Every
    # assertion above reads a mapping this test rebuilt, so all of them pass
    # unchanged if `_calculate_priority_score` uses 1.0, or swaps the two
    # factors. The ratio of two real scores, with every other input held
    # constant, is the only thing here that can tell those apart.
    ratio = _scored(TaskComplexity.COMPLEX) / _scored(TaskComplexity.SIMPLE)
    expected = applied[TaskComplexity.COMPLEX] / applied[TaskComplexity.SIMPLE]
    assert math.isclose(ratio, expected, rel_tol=1e-9), (
        f"the scheduler applies a complexity ratio of {ratio}, not the {expected} these "
        "constants declare -- the mapping and the code that uses it have diverged"
    )


def _scored(complexity) -> float:
    """`_calculate_priority_score` for one complexity, everything else fixed.

    A future-dated `scheduled_time` keeps the overdue bonus out: it is
    time-dependent, and it is added BEFORE the complexity factor multiplies,
    so leaving it in would make the ratio drift with the clock.
    """
    from datetime import datetime, timedelta, timezone

    from workflow_scheduler import ScheduledWorkflow, WorkflowPriority, WorkflowQueue, WorkflowStatus

    now = datetime.now(tz=timezone.utc)
    workflow = ScheduledWorkflow(
        id="t",
        name="t",
        template_id=None,
        user_message="t",
        scheduled_time=now + timedelta(hours=1),
        priority=WorkflowPriority.NORMAL,
        status=WorkflowStatus.PENDING,
        created_at=now,
        complexity=complexity,
    )
    return WorkflowQueue()._calculate_priority_score(workflow)


def _alias_names(enum_cls) -> set:
    """Names of *enum_cls* that resolve to a member reachable under another."""
    return set(enum_cls.__members__) - {m.name for m in enum_cls}


def _merging_dicts(tree: ast.AST, enum_cls, enum_alias: str):
    """Yield ``(lineno, written_names)`` for dicts whose keys silently merge.

    Keys are matched structurally -- an ``ast.Attribute`` on an ``ast.Name``
    equal to *enum_alias*. A string carrying the same text in a comment or a
    docstring is not an ``ast.Attribute`` and is never reached, which is the
    point: this guard's whole job is to find a construct, and a construct
    cannot be written in prose.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        written = [
            k.attr
            for k in node.keys
            if isinstance(k, ast.Attribute) and isinstance(k.value, ast.Name) and k.value.id == enum_alias
        ]
        if not written:
            continue
        resolved = {getattr(enum_cls, n) for n in written if hasattr(enum_cls, n)}
        if len(resolved) != len(written):
            yield node.lineno, written


_CONTROL_COLLAPSE = """
multiplier = {
    TaskComplexity.SIMPLE: 0.8,
    TaskComplexity.COMPLEX: 1.2,
    TaskComplexity.RESEARCH: 1.0,
}
"""

_CONTROL_PROSE = '''
"""A docstring naming TaskComplexity.RESEARCH and TaskComplexity.COMPLEX.

Mentioning TaskComplexity.RESEARCH twice, plus TaskComplexity.INSTALL, is
exactly the shape that satisfies a text-matching guard while changing nothing.
"""
# TaskComplexity.RESEARCH: retired alias, see #13806
NOTE = "TaskComplexity.RESEARCH and TaskComplexity.COMPLEX are the same member"
multiplier = {
    TaskComplexity.SIMPLE: 0.8,
    TaskComplexity.COMPLEX: 1.2,
}
'''


def test_the_detector_finds_a_planted_collapse():
    """Positive control: without it, a clean sweep proves only that it ran."""
    found = list(_merging_dicts(ast.parse(_CONTROL_COLLAPSE), _AliasedForControl, "TaskComplexity"))
    assert len(found) == 1, f"detector missed the planted collapse: {found}"
    assert sorted(found[0][1]) == ["COMPLEX", "RESEARCH", "SIMPLE"]


def test_the_detector_ignores_the_name_in_prose():
    """Contrast control: the string in a comment, docstring and str is not a key.

    This is the failure that has caught guard after guard here -- a check that
    greps is satisfied by the sentence describing the defect, so the guard goes
    green on a file that still contains it. The fixture carries every prose
    form (module docstring, `#` comment, string literal) alongside one honest
    two-key dict, and the detector must report nothing.
    """
    found = list(_merging_dicts(ast.parse(_CONTROL_PROSE), _AliasedForControl, "TaskComplexity"))
    assert found == [], f"detector matched prose rather than a dict key: {found}"
    # And the fixture really does contain the strings, so a pass is not an
    # artefact of an empty fixture.
    assert _CONTROL_PROSE.count("TaskComplexity.RESEARCH") == 4


def test_no_mapping_is_keyed_on_two_aliases_of_one_member():
    """Repo-wide: no dict literal's complexity keys merge. No exemptions.

    `workflow_scheduler.py` was exempted by name while #13806 was open; that
    exemption is gone, so this now covers the site the issue was filed about.
    A count of files read is asserted because a sweep that reaches nothing and
    a sweep that finds nothing produce the same empty list.
    """
    offenders = []
    read = 0
    for path in BACKEND.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        read += 1
        for lineno, written in _merging_dicts(tree, TaskComplexity, "TaskComplexity"):
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno} keys on {written}")

    assert read > 500, f"the sweep read only {read} files under {BACKEND} -- it did not run"
    assert not offenders, "dict literals whose TaskComplexity keys silently merge (#13806):\n" + "\n".join(offenders)


def test_the_enum_declares_no_duplicate_values_in_source():
    """Read the declaration, not the imported object.

    `test_task_complexity_has_no_alias_members` reads the runtime enum, which
    is the behaviour that matters. This reads `autobot_types.py` itself, so the
    two derivations share neither the enumeration nor the matching: a stale
    `.pyc`, a shadowing module on `sys.path` or a second `TaskComplexity`
    elsewhere would make the first test pass about the wrong object.
    """
    source = (BACKEND / "autobot_types.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "TaskComplexity"]
    assert len(classes) == 1, f"expected exactly one TaskComplexity declaration, found {len(classes)}"

    values = [
        stmt.value.value
        for stmt in classes[0].body
        if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str)
    ]
    assert values == ["simple", "complex"], f"TaskComplexity declares {values}"
    assert len(set(values)) == len(values), f"duplicate values re-create the #13806 aliases: {values}"
