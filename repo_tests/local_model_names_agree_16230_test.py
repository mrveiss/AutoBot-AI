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


def _local_constant_values(source: str | None = None) -> tuple[str, ...]:
    """The string value of every module-level ``LOCAL_*`` constant.

    Both ``NAME = "literal"`` and ``NAME: str = "literal"`` are read. Only the
    plain form was, and ``ast.AnnAssign`` is a different node type — so
    ``LOCAL_FOO: str = "foo"`` was invisible, and adding one in that style would
    have left this guard reporting agreement over a constant it never saw
    (#16230 review). A computed value is still ignored: it is not the kind of
    stray constant this guard exists to catch.

    Takes *source* so the detector can be driven against a fixture rather than
    only against the live file — a detector checked only on today's tree proves
    today's tree, not the detector.
    """
    text = source if source is not None else _SSOT_CONSTANTS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(text)
    values = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if not (isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id.startswith("LOCAL_"):
                values.append(node.value.value)
    return tuple(values)


# ---------------------------------------------------------------------------
# Contrast fixtures. Reading the live file proves what ssot_constants.py says
# today and nothing about whether the detector would notice a change.
# ---------------------------------------------------------------------------

_FIXTURE_PLAIN = 'LOCAL_ALPHA = "alpha"\nOTHER = "not-local"\n'
_FIXTURE_ANNOTATED = 'LOCAL_BETA: str = "beta"\n'
_FIXTURE_COMPUTED = 'LOCAL_GAMMA = "gam" + "ma"\n'


def test_the_detector_reads_a_plain_assignment():
    assert _local_constant_values(_FIXTURE_PLAIN) == ("alpha",)


def test_the_detector_reads_an_annotated_assignment():
    """The positive half of the review finding: this returned () before."""
    assert _local_constant_values(_FIXTURE_ANNOTATED) == ("beta",)


def test_the_detector_ignores_a_computed_value():
    """The negative half — broadening the parser must not make it match anything."""
    assert _local_constant_values(_FIXTURE_COMPUTED) == ()


def test_a_missing_name_is_detectable_at_all():
    """The whole assertion, run against a fixture whose answer is known.

    Without this, every other test here passes because the tree happens to be
    correct today, and a detector that silently stopped detecting would look
    identical.
    """
    found = set(_local_constant_values(_FIXTURE_PLAIN + _FIXTURE_ANNOTATED))
    assert sorted(found - {"alpha"}) == ["beta"], "a LOCAL_* value absent from the set was not reported"
    assert not (found - {"alpha", "beta"}), "the detector invented a value no fixture declares"


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
