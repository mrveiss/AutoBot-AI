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
    known = hook.KNOWN_LARGE
    recorded = baseline.RATCHET_BASELINE

    only_in_hook = {rel: known[rel] for rel in set(known) - set(recorded)}
    only_in_baseline = {rel: recorded[rel] for rel in set(recorded) - set(known)}
    disagreeing = {
        rel: (known[rel], recorded[rel]) for rel in set(known) & set(recorded) if known[rel] != recorded[rel]
    }

    # The message names BOTH values and asserts NO direction. Lowering a baseline used
    # to fail a test called "no ceiling may be raised", sending the reader after a raise
    # that never happened -- a wrong diagnosis costs more than a vague one.
    assert not (only_in_hook or only_in_baseline or disagreeing), (
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
