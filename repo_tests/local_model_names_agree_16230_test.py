# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every ``LOCAL_*`` constant in ``ssot_constants.py`` must be in ``LOCAL_MODEL_NAMES`` (#16230).

``autobot_shared.local_models.LOCAL_MODEL_NAMES`` replaced the zero-price
entries a hardcoded pricing table used to carry for local models (#16316):
``is_local_model()`` is checked before any pricing lookup, so a name missing
from this set is not "unpriced" but "not recognised as local", and
``ingest_cost_event``/``calculate_cost`` raise ``UnpricedModel`` for it — an
agent running a real local model has its runs blocked, and nothing says why.

The set is a hand-picked literal, chosen deliberately over deriving it from
``llm_shared.optimization.router.is_local_provider()`` because that function
takes a ``ProviderType`` enum, not a model-name string, and no model-name to
provider-type resolver exists anywhere in this codebase (confirmed by grep at
the time of #16230) — building one to derive a 15-entry set would be more
machinery than the set itself. A hand-picked literal has exactly the failure
mode the table it replaced had: a sixteenth ``LOCAL_*`` constant can be added
to ``ssot_constants.py`` without anyone remembering to add it here too. This
guard is the thing that stands in for that memory.

Static, not runtime
--------------------

``ssot_constants.py`` is parsed with ``ast``, not imported, so this guard's
result does not depend on import side effects and reads exactly what a human
skimming the file would read: every module-level ``LOCAL_XXX = "..."``
assignment. ``autobot_shared.local_models`` is imported directly — it is a
plain frozenset with a single cheap import of ``ssot_constants``, unlike the
backend services this guard must not need to construct.
"""

from __future__ import annotations

import ast

from repo_tests._paths import repo_root

from autobot_shared.local_models import LOCAL_MODEL_NAMES

_REPO = repo_root()
_SSOT_CONSTANTS_FILE = _REPO / "autobot_shared" / "ssot_constants.py"

#: Below this the enumeration has stopped describing ``ssot_constants.py`` and
#: the agreement assertion no longer means what it claims. 15 constants exist
#: today; the floor is deliberately under that so adding one is not a reason
#: to edit this test, while a parser regression returning a handful still fails.
_MIN_LOCAL_CONSTANTS = 10


def _local_constant_values() -> tuple[str, ...]:
    """The string value of every module-level ``LOCAL_*`` constant.

    Only plain ``NAME = "literal"`` assignments are considered — every
    existing ``LOCAL_*`` entry is one, and a computed value would not be the
    kind of stray constant this guard exists to catch.
    """
    tree = ast.parse(_SSOT_CONSTANTS_FILE.read_text(encoding="utf-8"))
    values = []
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not (isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.startswith("LOCAL_"):
                values.append(node.value.value)
    return tuple(values)


def test_the_constant_table_is_read_and_is_not_empty():
    found = _local_constant_values()

    assert len(found) >= _MIN_LOCAL_CONSTANTS, (
        f"only {len(found)} LOCAL_* constants parsed out of {_SSOT_CONSTANTS_FILE.name}; "
        "the agreement assertion below would range over almost nothing"
    )


def test_every_local_constant_in_ssot_is_in_local_model_names():
    """The defect itself: a LOCAL_* constant this set does not recognise."""
    found = _local_constant_values()
    assert found, "no LOCAL_* constants parsed; nothing was checked"

    missing = sorted(set(found) - LOCAL_MODEL_NAMES)

    assert not missing, (
        "ssot_constants.py defines LOCAL_* constant(s) that autobot_shared.local_models."
        f"LOCAL_MODEL_NAMES does not include: {missing} -- a cost event naming one of these "
        "will raise UnpricedModel instead of resolving to $0. Add it to LOCAL_MODEL_NAMES."
    )
