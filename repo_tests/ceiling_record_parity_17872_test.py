# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Each size gate's two ceiling records must be EQUAL, not merely non-raising (#17872).

Both gates keep their ceilings twice on purpose, and both say so: *"neither copy is
derived from the other at runtime"*, because *"a list only ever compared against itself
can drift anywhere"*. The hook's copy is anchored to real file sizes by
``audit_ceilings``; the baseline copy is anchored by the ratchet test. Two independent
anchors are what make a raise impossible to sneak through one file.

That mechanism only holds if the two are compared **both ways**, and on the Python side
they were not. `test_no_ceiling_may_exceed_its_baseline` (renamed here from
`test_no_ceiling_may_be_raised`, which named a cause it cannot establish) fires on
`ceiling > baseline` alone, so
raising the BASELINE passed, and `test_no_entry_may_be_added` compares keys in one
direction only. The shell gate has had the equality assertion all along
(`shell_file_size_ratchet_test.py`); the Python gate had no equality assertion at all.

`test_no_ceiling_may_be_raised` was also RENAMED to
`test_no_ceiling_may_exceed_its_baseline`, and its message no longer claims a cause:
`ceiling > baseline` is produced equally by a raised ceiling and a lowered baseline, and
#17725 was the second -- so the reader of a failure was sent after a raise that never
happened. A wrong diagnosis costs more than a vague one. Its predicate is unchanged and
still one-directional on purpose; the reverse direction is this file's job, because
writing it in both places would make two records of one check -- the very shape #17872 is
about. That test's docstring is one line because its file sits at the 600-line hard limit
with no KNOWN_LARGE entry, so the rationale lives here, where there is room for it.

Asserted here for BOTH pairs rather than only the one that was broken: the defect was
two hand-kept copies per gate with an asymmetric comparison, and a fix that covers one
gate leaves the identical arrangement one directory away with nothing pointing at it.

**This file now owns equality for both gates.** Review on #17882 caught the PR's own
thesis turned on itself: parametrising over ``"shell"`` made a second record of a check
``shell_file_size_ratchet_test.test_the_two_copies_of_the_ceilings_agree`` already
performed. Reasoning about the file being edited was right for Python, where no equality
test existed -- that absence is why #17872 was filed -- and silently wrong for shell,
where one did. That test is removed and its insight kept, because it stated something
neither of mine did: **the gap between a lowered hook and an unlowered mirror is exactly
the lines just cut, and it is spendable.** That is what a disagreement *means*, so it
belongs in the failure message a reader actually sees.

Why the reach check is a non-empty assert and not a declared floor (``repo_tests._reach``):
both records only ever SHRINK -- the hook's header says *"THIS MAPPING ONLY SHRINKS --
entries leave when the file reaches MAX_LINES"* -- so a static floor near today's size
fails the first time a file is legitimately split, and a floor an order of magnitude below
is the number-chosen-by-feel that ``declare``'s own docstring names as that mechanism's
recurring failure. A floor needing to be lowered every time the ratchet succeeds is an
incentive against doing the work. Nor can these records degrade *partially*: each is a
literal dict executed by ``exec_module``, so a broken loader raises rather than returning
a subset. Empty is the only reachable silent degradation. **What would reopen the floor
question: a loader that parses or filters rather than executing a literal.**

Left alone deliberately: ``test_no_ceiling_may_exceed_its_baseline`` here and
``test_no_ceiling_exceeds_its_recorded_baseline`` in the shell file are both logically
subsumed by this equality -- if the records are equal, neither can exceed the other. They
are kept because each gives the common direction a specific diagnosis, and because the
redundancy is pre-existing and symmetric across both gates rather than something this
change introduced. Recorded so the next reader does not have to re-derive it (#17882).

The tree-anchored direction -- every file over ``MAX_LINES`` must be recorded -- is owned
by ``python_file_size_ratchet_test.test_recorded_ceilings_match_the_files_today``, which
does fail on an emptied record (mutation: 3 failed). Not asserted here, for the same
reason the shell duplicate was removed.
"""

import importlib
import importlib.util
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

#: ``(hook, baseline module)``. The hook is the authority for ``KNOWN_LARGE`` in both
#: cases even though they obtain it differently -- Python executes a sibling data module,
#: shell declares the mapping inline. That is a data-source difference, not a structural
#: one, so it is a parameter here. No entry counts are quoted: both records shrink by
#: design, so a count written here would go stale for the same reason a numeric floor
#: would be wrong.
_PAIRS = {
    "python": ("scripts/check_python_file_size.py", "repo_tests.python_file_size_ratchet_baseline"),
    "shell": ("scripts/check_shell_file_size.py", "repo_tests.shell_file_size_ratchet_baseline"),
    # #17885: the frontend gate is registered here at birth rather than after a
    # drift. Its hook loads KNOWN_LARGE from a sibling data module, as Python's
    # does, so the data-source difference this mapping already tolerates covers it.
    "frontend": ("scripts/check_frontend_file_size.py", "repo_tests.frontend_file_size_ratchet_baseline"),
}


def _load_hook(rel: str):
    """Load a gate by path -- ``scripts/`` is not an importable package."""
    spec = importlib.util.spec_from_file_location(f"_ceilings_{rel.replace('/', '_')}", repo_root() / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(params=sorted(_PAIRS), ids=sorted(_PAIRS))
def pair(request):
    hook_rel, baseline_mod = _PAIRS[request.param]
    return _load_hook(hook_rel), importlib.import_module(baseline_mod), hook_rel, baseline_mod


def _disagreement_report(known: dict, recorded: dict, hook_rel: str, baseline_mod: str) -> str:
    """The failure message for one pair of ceiling records, or ``""`` when they agree.

    Split out because **the message is the deliverable** (#17872), and a message only ever
    produced by a real disagreement in the checked-in records cannot be asserted on: this
    takes its two records as arguments, so the tests below can feed it synthetic ones.
    """
    only_in_hook = {rel: known[rel] for rel in set(known) - set(recorded)}
    only_in_baseline = {rel: recorded[rel] for rel in set(recorded) - set(known)}
    disagreeing = {
        rel: (known[rel], recorded[rel]) for rel in set(known) & set(recorded) if known[rel] != recorded[rel]
    }
    if not (only_in_hook or only_in_baseline or disagreeing):
        return ""

    # Names BOTH values and asserts NO direction.
    return (
        f"the two ceiling records disagree.\n"
        f"  hook:     {hook_rel} (KNOWN_LARGE, {len(known)} entries)\n"
        f"  baseline: {baseline_mod.replace('.', '/')}.py (RATCHET_BASELINE, {len(recorded)} entries)\n"
        f"  only in the hook:     {sorted(only_in_hook)}\n"
        f"  only in the baseline: {sorted(only_in_baseline)}\n"
        f"  disagreeing (hook, baseline): {disagreeing}\n"
        "Both are checked in by hand and neither derives from the other, deliberately: "
        "two independent anchors are what stop a ceiling being raised by editing one "
        "file. Lower BOTH in the same commit, and never raise either -- the gap between "
        "a lowered hook and an unlowered mirror is exactly the lines just cut, and it is "
        "spendable."
    )


def _empty_record_failure(known: dict, recorded: dict, hook_rel: str, baseline_mod: str) -> str:
    """Message when either record is empty, else ``""`` -- the reach half of this guard.

    Equality is satisfied by two EMPTY dicts, so without this the file reports agreement
    having read nothing (review on #17882). Why a non-empty assert rather than a declared
    floor, and what would reopen that question, is in the module docstring.
    """
    labels = ((hook_rel, known), (f"{baseline_mod.replace('.', '/')}.py", recorded))
    empty = [label for label, record in labels if not record]
    if not empty:
        return ""
    return (
        "a ceiling record is EMPTY, so this guard has compared nothing: " + ", ".join(empty) + ". "
        "Two empty records are equal, which is why emptiness is checked before equality -- "
        "a pass here would license 'the two records agree' on the strength of having read "
        "neither. Check the loader before touching the records."
    )


def test_the_two_records_are_equal(pair) -> None:
    """Equality, not "neither exceeds the other" written twice.

    Two directional assertions ARE equality, expressed awkwardly, and the awkward form
    is what hid the gap: one direction was written and the other was not. Equality
    cannot be half-implemented.

    It also subsumes the missing-key case in both directions -- the Python key check
    skipped `rel not in RATCHET_BASELINE` silently, so an entry present in one record
    and absent from the other was invisible.
    """
    hook, baseline, hook_rel, baseline_mod = pair
    known, recorded = hook.KNOWN_LARGE, baseline.RATCHET_BASELINE

    # *"A list only ever compared against itself can drift anywhere"* -- the baselines' own
    # words for why the two copies exist. If a future edit pointed both halves of a pair at
    # one module, or aliased one record to the other, equality would pass trivially and this
    # guard would be the thing that looked fine. Two files, two objects, asserted.
    assert known is not recorded, f"{hook_rel} and {baseline_mod} yielded the SAME object"
    hook_file, baseline_file = Path(hook.__file__).resolve(), Path(baseline.__file__).resolve()
    assert hook_file != baseline_file, f"both records were read from one file: {hook_file}"

    # Reach before findings: equality over two empty dicts is a pass that means nothing.
    unread = _empty_record_failure(known, recorded, hook_rel, baseline_mod)
    assert not unread, unread

    report = _disagreement_report(known, recorded, hook_rel, baseline_mod)
    assert not report, report


# ---------------------------------------------------------------------------
# The reporter itself, driven on synthetic records. Without these, the test
# above passes on a tree that already agrees and proves nothing about what
# happens when it stops agreeing -- which is the only case that matters.
# ---------------------------------------------------------------------------

_HOOK = "scripts/check_python_file_size.py"
_BASE = "repo_tests.python_file_size_ratchet_baseline"


def test_agreeing_records_produce_no_report() -> None:
    """The contrast case: without it, a reporter that always complains would pass below."""
    assert _disagreement_report({"a.py": 100}, {"a.py": 100}, _HOOK, _BASE) == ""


def test_a_one_sided_edit_names_both_values_and_no_direction() -> None:
    """The exact #17725 edit: the baseline moved, the hook did not.

    Asserts the MESSAGE, not just that something failed. The old cross-check failed
    too -- under a name that sent the reader after a raise that never happened.
    """
    report = _disagreement_report({"big.py": 1050}, {"big.py": 1028}, _HOOK, _BASE)
    assert report, "a disagreement produced no report"
    assert "big.py" in report, f"the disagreeing file is not named: {report}"
    assert "(1050, 1028)" in report, (
        "the message must carry both values in (hook, baseline) order so the reader "
        f"knows which file to edit: {report}"
    )
    assert (
        _HOOK in report and "python_file_size_ratchet_baseline.py" in report
    ), f"both records must be named -- editing the wrong one is the defect: {report}"
    assert (
        "disagree" in report.splitlines()[0]
    ), f"the headline must state the symmetric fact, not a direction: {report.splitlines()[0]}"


@pytest.mark.parametrize(
    ("known", "recorded", "expected_line"),
    [
        pytest.param({"solo.py": 1}, {}, "only in the hook:     ['solo.py']", id="hook-only"),
        pytest.param({}, {"solo.py": 1}, "only in the baseline: ['solo.py']", id="baseline-only"),
    ],
)
def test_a_key_in_one_record_only_is_reported(known: dict, recorded: dict, expected_line: str) -> None:
    """Both directions. The Python key check covered one and skipped the other in silence."""
    report = _disagreement_report(known, recorded, _HOOK, _BASE)
    assert expected_line in report, f"expected {expected_line!r} in:\n{report}"


def test_two_empty_records_are_not_agreement() -> None:
    """The hole review found: ``{} == {}`` is True and licenses nothing."""
    message = _empty_record_failure({}, {}, _HOOK, _BASE)
    assert message, "two empty records produced no reach failure"
    assert (
        _HOOK in message and "python_file_size_ratchet_baseline.py" in message
    ), f"both empty records must be named: {message}"
    assert _disagreement_report({}, {}, _HOOK, _BASE) == "", (
        "equality must still hold for two empty records -- if this starts failing, the "
        "emptiness check is no longer what is catching this case, and the reason this "
        "guard is split in two has been lost"
    )


@pytest.mark.parametrize(
    ("known", "recorded", "expect_named"),
    [
        pytest.param({}, {"a.py": 1}, _HOOK, id="hook-empty"),
        pytest.param({"a.py": 1}, {}, "python_file_size_ratchet_baseline.py", id="baseline-empty"),
    ],
)
def test_one_empty_record_names_which_one(known: dict, recorded: dict, expect_named: str) -> None:
    """One side empty must name THAT side -- the #17725 lesson was editing the wrong copy."""
    message = _empty_record_failure(known, recorded, _HOOK, _BASE)
    assert expect_named in message, f"expected {expect_named!r} to be named in:\n{message}"


def test_populated_records_produce_no_reach_failure() -> None:
    """Contrast case. Without it, a reach check that always complains passes the three above."""
    assert _empty_record_failure({"a.py": 1}, {"a.py": 1}, _HOOK, _BASE) == ""
