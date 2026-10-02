# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Each size gate's two ceiling records must be EQUAL, not merely non-raising (#17872).

Both gates keep their ceilings twice on purpose, and both say so: *"neither copy is
derived from the other at runtime"*, because *"a list only ever compared against itself
can drift anywhere"*. The hook's copy is anchored to real file sizes by
``audit_ceilings``; the baseline copy is anchored by the ratchet test. Two independent
anchors are what make a raise impossible to sneak through one file.

That mechanism only holds if the two are compared **both ways**, and on the Python side
they were not. `test_no_ceiling_may_be_raised` fires on `ceiling > baseline` alone, so
raising the BASELINE passed, and `test_no_entry_may_be_added` compares keys in one
direction only. The shell gate has had the equality assertion all along
(`shell_file_size_ratchet_test.py`); the Python gate had no equality assertion at all.

Asserted here for BOTH pairs rather than only the one that was broken: the defect was
two hand-kept copies per gate with an asymmetric comparison, and a fix that covers one
gate leaves the identical arrangement one directory away with nothing pointing at it.
"""

import importlib
import importlib.util

import pytest
from repo_tests._paths import repo_root

#: ``(hook, baseline module)``. The hook is the authority for ``KNOWN_LARGE`` in both
#: cases even though they obtain it differently -- Python loads 479 entries from
#: ``scripts/python_file_size_known_large.py``, shell declares 10 inline. That is a
#: data-source difference, not a structural one, so it is a parameter here.
_PAIRS = {
    "python": ("scripts/check_python_file_size.py", "repo_tests.python_file_size_ratchet_baseline"),
    "shell": ("scripts/check_shell_file_size.py", "repo_tests.shell_file_size_ratchet_baseline"),
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

    Split out from the assertion because **the message is the deliverable** (#17872): the
    old failure said *"no ceiling may be raised"* for an edit that raised nothing, and a
    wrong diagnosis costs more than a vague one. A message only ever produced by a real
    disagreement in the checked-in records cannot be asserted on, so the reporter takes
    its two records as arguments and the tests below feed it synthetic ones.
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
        "file. Lower BOTH in the same commit, and never raise either."
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
    report = _disagreement_report(hook.KNOWN_LARGE, baseline.RATCHET_BASELINE, hook_rel, baseline_mod)
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
