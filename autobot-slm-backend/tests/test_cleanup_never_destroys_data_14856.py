# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Provisioning cleanup must never be able to delete live data (#14856).

Re-running provisioning is the natural rescue for a host broken by a partial
code-sync — and that is exactly the state where the `role_*_active` facts are
most likely to be missing or wrong. So the recovery path must not be able to
destroy the data it is being run to save.

Two fail-destructive shapes are pinned out:

  * a `state: absent` gated on `lookup('vars', ..., default=false)`, where an
    UNDEFINED fact takes the delete branch
  * an unconditional `state: absent` on a component directory, which assumes
    every host that has ever existed keeps no state there

On a deployed host these paths carry `data/` with unified_memory.db,
conversation_files.db, transcriber.db, service-keys and .slm_keys, so
`state: absent` on the parent takes them with it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_SHARED = Path(__file__).resolve().parents[1] / "ansible" / "roles" / "_shared" / "tasks"
_WRONG_NODE = _SHARED / "clean_wrong_node_dir.yml"
_LEGACY = _SHARED / "clean_legacy_dir.yml"


def _tasks(path: Path) -> list[dict]:
    assert path.is_file(), f"file under test is missing: {path}"
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    assert loaded, f"{path.name} defines no tasks — this guard would pass vacuously"
    return [t for t in loaded if isinstance(t, dict)]


def _deletions(tasks: list[dict]) -> list[dict]:
    out = []
    for task in tasks:
        spec = task.get("ansible.builtin.file") or task.get("file") or {}
        if isinstance(spec, dict) and spec.get("state") == "absent":
            out.append(task)
    return out


@pytest.mark.parametrize("path", [_WRONG_NODE, _LEGACY], ids=["wrong_node", "legacy"])
def test_no_deletion_is_gated_on_a_defaulting_lookup(path: Path) -> None:
    """`default=false` on the gating fact makes UNDEFINED mean delete."""
    for task in _deletions(_tasks(path)):
        conditions = task.get("when")
        rendered = " ".join(conditions) if isinstance(conditions, list) else str(conditions)
        flat = rendered.replace(" ", "")
        # Both spellings: the lookup form `default=false` and the filter form
        # `default(false)`. Either one means "when we do not know, delete".
        #
        # No exceptions carved out: a rule with exceptions stops being checkable.
        # Where a defaulting expression is genuinely needed, compute it into a
        # named fact first and gate on that — which is what both files now do.
        for bad in ("default=false", "default(false)"):
            assert bad not in flat, (
                f"{path.name}: a state=absent task is gated on {bad}, so an unknown value takes the "
                f"delete branch. Compute the decision into a fact with a safe default instead:\n"
                f"  {task.get('name')}"
            )


@pytest.mark.parametrize("path", [_WRONG_NODE, _LEGACY], ids=["wrong_node", "legacy"])
def test_no_deletion_is_unconditional(path: Path) -> None:
    """An unconditional removal cannot account for a host that holds state."""
    for task in _deletions(_tasks(path)):
        assert task.get("when"), (
            f"{path.name}: '{task.get('name')}' removes a directory unconditionally — "
            "it cannot know whether this host keeps data there"
        )


def test_wrong_node_deletion_requires_the_fact_to_be_defined() -> None:
    """Undefined must mean 'unknown', never 'inactive'."""
    conds = " ".join(_deletions(_tasks(_WRONG_NODE))[0]["when"])
    assert "is not none" in conds, (
        "the wrong-node deletion does not require the role fact to be defined, so a play run "
        "without the role-active facts would delete the directory"
    )


def test_wrong_node_deletion_is_blocked_by_persistent_data() -> None:
    """The backstop for the fact simply being WRONG.

    #14513, #14560, #14666 and #14682 were each a case of one of these facts
    being incorrect. When it is wrong in the false direction, only this
    condition stands between a re-run and a deleted database.
    """
    conds = " ".join(_deletions(_tasks(_WRONG_NODE))[0]["when"])
    assert (
        "stat.exists" in conds
    ), "the wrong-node deletion does not check for a data/ directory, so a wrong fact deletes live data"


def test_legacy_retirement_migrates_before_removing() -> None:
    """Retiring a legacy path is a migration, not a deletion."""
    tasks = _tasks(_LEGACY)
    names = [str(t.get("name", "")) for t in tasks]
    assert any("MIGRATE" in n for n in names), "legacy cleanup no longer migrates data to the canonical path"

    migrate_at = next(i for i, n in enumerate(names) if "MIGRATE" in n)
    delete_at = next(i for i, t in enumerate(tasks) if t in _deletions(tasks))
    assert migrate_at < delete_at, "the legacy directory is removed before its data is migrated"

    delete_when = " ".join(_deletions(tasks)[0]["when"].split())
    assert "_legacy_has_data" in delete_when, "the legacy removal does not consider whether the path held data"
