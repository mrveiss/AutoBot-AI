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

import pytest
from repo_tests._glob_declared_uncovered import GLOB_DECLARED_UNCOVERED
from repo_tests._paths import repo_root
from repo_tests._ratchet_base import base_table, literal_in
from repo_tests._reach import declare

from autobot_shared.isolated_git import git, make_repo

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
    # 29 keys when written. skips=19 is a SHRINK allowance on a set meant to reach zero as the debt is
    # paid, so the floor may trail the population; it is not a count of items the guard cannot complete.
    floor=10,
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


def grown_against_base(root: Path, now: dict[str, Any]) -> dict[str, list[str]]:
    """What *now* added to the record relative to the base commit of *root* (BaseUnavailable if unreadable)."""
    base = base_table(root, (_RECORD,), _NAME)
    return grown_entries(now, base)


def test_the_record_did_not_grow_against_the_base() -> None:
    base = base_table(repo_root(), (_RECORD,), _NAME)
    assert isinstance(base, dict) and base, "the base read returned no record; the guard would pass vacuously"
    grown = grown_entries(GLOB_DECLARED_UNCOVERED, base)
    assert not grown, _complaint(grown)
    REACH.completed(REACH.examined(repo_root()))


def _commit_record(repo: Path, body: str) -> str:
    (repo / _RECORD).parent.mkdir(parents=True, exist_ok=True)
    (repo / _RECORD).write_text(body, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "c")
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def test_the_base_read_flags_a_key_added_in_a_real_git_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fails if the guard stopped reading the base (e.g. compared the record with itself)."""
    make_repo(tmp_path)
    first = _commit_record(tmp_path, f'{_NAME} = {{"*.md": ({{"a_test.py"}}, "why")}}\n')
    now_src = f'{_NAME} = {{"*.md": ({{"a_test.py"}}, "why"), "*.service": ({{"b_test.py"}}, "why")}}\n'
    _commit_record(tmp_path, now_src)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("AUTOBOT_RATCHET_BASE_SHA", first)
    assert grown_against_base(tmp_path, literal_in(now_src, _NAME)) == {"*.service": ["b_test.py"]}  # type: ignore[arg-type]


def test_a_planted_added_glob_key_is_caught() -> None:
    base = {"*.md": ({"a_test.py"}, "why")}
    now = {**base, "*.service": ({"b_test.py"}, "why")}
    assert grown_entries(now, base) == {"*.service": ["b_test.py"]}
    assert "dedicated workflow" in _complaint(grown_entries(now, base))
    assert grown_entries({**base, "*.service": (set(), "why")}, base) == {"*.service": []}, "an empty new key is a key"


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


def test_a_record_absent_from_the_base_commit_fails_the_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard's own read, not just ``grown_entries({})``: no record at the base means every key is added."""
    make_repo(tmp_path)
    (tmp_path / "other.txt").write_text("x\n", encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base without the record")
    first = git(tmp_path, "rev-parse", "HEAD").stdout.strip()
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("AUTOBOT_RATCHET_BASE_SHA", first)
    grown = grown_against_base(tmp_path, GLOB_DECLARED_UNCOVERED)
    assert set(grown) == set(GLOB_DECLARED_UNCOVERED), "a missing base record must read every key as added"
