# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``GLOB_DECLARED_UNCOVERED`` only shrinks, held against the merge base (#21183).

``repo_tests/_glob_declared_uncovered.py`` calls the record DEBT that "only ever shrinks", and
``glob_declared_reads_15900_test`` checks every entry is true, but nothing stopped a PR adding
one: a new glob key, or a new guard under an existing key. Either means that guard silently
does not run when its tree changes. #20980 and #20912 each did it and only a reviewer saw.

Each key's guard set is compared with the same record at the base commit
(``_ratchet_base.base_table``, which raises ``BaseUnavailable`` when the base cannot be read
rather than passing as "nothing grew"). Removals pass; additions fail.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from repo_tests._glob_declared_uncovered import GLOB_DECLARED_UNCOVERED
from repo_tests._paths import repo_root
from repo_tests._ratchet_base import base_table, literal_in
from repo_tests._reach import declare

_RECORD = "repo_tests/_glob_declared_uncovered.py"
_NAME = "GLOB_DECLARED_UNCOVERED"


def _glob_keys(root: Path) -> list[str]:
    """The record's glob keys as read from *root*'s copy of the file; none if *root* has no record."""
    record = root / _RECORD
    if not record.is_file():
        return []
    return sorted(literal_in(record.read_text(encoding="utf-8"), _NAME))  # type: ignore[call-overload]


REACH = declare(
    "glob-declared-uncovered-entries",
    discover=_glob_keys,
    floor=10,  # 29 keys when written; the record shrinks as debt is paid, so skips=19 lets it fall to the floor
    skips=19,
    what="glob keys in the uncovered-debt record",
)

_ROUTES = (
    "Two legitimate routes: (1) cover the tree in the python path filter "
    "(.github/ python filter, see python_filter_covers_its_guards_test), or "
    "(2) run the guard from a dedicated workflow and record it in "
    "GLOB_RUN_BY_A_DEDICATED_WORKFLOW (#17488). Adding to GLOB_DECLARED_UNCOVERED is not a route."
)


def grown_entries(now: dict[str, Any], base: dict[str, Any]) -> dict[str, list[str]]:
    """``{glob: guards}`` added against *base*: a new key lists all its guards, an old key only the new ones."""
    return {
        glob: sorted(set(value[0]) - set(base[glob][0]) if glob in base else set(value[0]))
        for glob, value in now.items()
        if glob not in base or set(value[0]) - set(base[glob][0])
    }


def _complaint(grown: dict[str, list[str]]) -> str:
    return f"{_NAME} grew against the base (glob: added guards): {grown}. It only shrinks. {_ROUTES}"


def test_the_record_did_not_grow_against_the_base() -> None:
    base = base_table(repo_root(), (_RECORD,), _NAME)
    grown = grown_entries(GLOB_DECLARED_UNCOVERED, base)
    assert not grown, _complaint(grown)
    REACH.completed(REACH.examined(repo_root()))


def test_a_planted_added_glob_key_is_caught() -> None:
    base = {"*.md": ({"a_test.py"}, "why")}
    now = {**base, "*.service": ({"b_test.py"}, "why")}
    assert grown_entries(now, base) == {"*.service": ["b_test.py"]}
    assert "dedicated workflow" in _complaint(grown_entries(now, base))


def test_a_planted_added_guard_under_an_existing_key_is_caught() -> None:
    base = {"*.md": ({"a_test.py"}, "why")}
    now = {"*.md": ({"a_test.py", "b_test.py"}, "why")}
    assert grown_entries(now, base) == {"*.md": ["b_test.py"]}


def test_a_planted_removal_passes() -> None:
    base = {"*.md": ({"a_test.py", "b_test.py"}, "why"), "*.j2": ({"c_test.py"}, "why")}
    assert grown_entries({"*.md": ({"a_test.py"}, "why")}, base) == {}
    assert grown_entries(base, base) == {}


def test_a_missing_base_record_reads_every_entry_as_added() -> None:
    assert set(grown_entries(GLOB_DECLARED_UNCOVERED, {})) == set(GLOB_DECLARED_UNCOVERED)
