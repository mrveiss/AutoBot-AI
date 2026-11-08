# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Each size gate keeps its ceilings in ONE record, and that record is read (#17872, #19544).

#17872 found two hand-kept copies per gate compared asymmetrically. #19544 removed the
second copy: "no entry added" and "no ceiling raised" are checked against the SAME table at
the base commit (``repo_tests/_ratchet_base.py``), which a copy only imitated, so the
equality this file used to assert has nothing left to compare.

What remains worth asserting, for every gate rather than only the one that was broken:

* the single record is non-empty -- an emptied table disables the gate while looking clean,
  and nothing else compares against it;
* no gate still names a second record (``RATCHET_REL``), which would tell a developer to edit
  a file that no longer exists.

That no hand-written ceiling table is re-added anywhere is owned by
``no_second_ceiling_table_19544_test.py``.
"""

import importlib.util

import pytest
from repo_tests._paths import repo_root

_GATES = {
    "python": "scripts/check_python_file_size.py",
    "shell": "scripts/check_shell_file_size.py",
    "frontend": "scripts/check_frontend_file_size.py",
}


def _load_hook(rel: str):
    """Load a gate by path -- ``scripts/`` is not an importable package."""
    spec = importlib.util.spec_from_file_location(f"_ceilings_{rel.replace('/', '_')}", repo_root() / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(params=sorted(_GATES), ids=sorted(_GATES))
def gate(request):
    return _load_hook(_GATES[request.param])


def test_the_single_record_is_not_empty(gate) -> None:
    """An empty table passes every comparison made against it."""
    assert gate.KNOWN_LARGE, f"{gate.SELF_REL}: KNOWN_LARGE is empty, so the gate exempts and checks nothing"


def test_no_gate_names_a_second_record(gate) -> None:
    """A leftover ``RATCHET_REL`` points a developer at a copy that does not exist (#19544)."""
    assert not hasattr(gate, "RATCHET_REL"), f"{gate.SELF_REL} still names a second ceiling record"
