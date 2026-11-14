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
from repo_tests._ratchet_base import BaseUnavailable, base_table, literal_in
from repo_tests._reach import ReachFloorError, declare

from autobot_shared.isolated_git import git, make_repo

_RECORD = "repo_tests/_glob_declared_uncovered.py"
_NAME = "GLOB_DECLARED_UNCOVERED"


def _record_read(root: Path) -> list[str]:
    """The record's own path when *root* holds it and its table parsed to a dict, else nothing.

    The reach is what the guard READ, not how much debt remains (#21347): a paid-off record is an
    empty dict, which is a successful read and must not fail a floor. A missing file, an
    unparseable one, or one without the assignment reads nothing, so the floor still fires.
    """
    record = root / _RECORD
    if not record.is_file():
        return []
    try:
        table = literal_in(record.read_text(encoding="utf-8"), _NAME)
    except (SyntaxError, ValueError, TypeError, BaseUnavailable):
        return []
    return [_RECORD] if isinstance(table, dict) else []


REACH = declare(
    "glob-declared-uncovered-entries",
    discover=_record_read,
    # One item: the record, read and parsed. Pinned at 1 with no skips or growth because the population is
    # exactly one by construction, so the floor sits at it and 0 (unread) is the only failure.
    floor=1,
    what="parsed copies of the uncovered-debt record",
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


def _base_record(root: Path) -> dict[str, Any]:
    """The record at the base commit of *root*: a dict, EMPTY when the debt is paid or the base has no record.

    Only the type is asserted, never the truthiness (#21347). An empty base is the legitimate end
    state of a record that only shrinks, and an absent one already reads as ``{}`` from ``base_table``,
    so every current key is an addition and the guard still fails instead of passing vacuously.
    """
    base = base_table(root, (_RECORD,), _NAME)
    assert isinstance(base, dict), f"the base read returned {type(base).__name__}, not the record's dict"
    return base


def grown_against_base(root: Path, now: dict[str, Any]) -> dict[str, list[str]]:
    """What *now* added to the record relative to the base commit of *root* (BaseUnavailable if unreadable)."""
    return grown_entries(now, _base_record(root))


def check_record(root: Path, now: dict[str, Any]) -> None:
    """The live check: the record was read (reach), and *now* added nothing to it against the base."""
    REACH.completed(REACH.examined(root))
    grown = grown_against_base(root, now)
    assert not grown, _complaint(grown)


def test_the_record_did_not_grow_against_the_base() -> None:
    check_record(repo_root(), GLOB_DECLARED_UNCOVERED)


def _commit_record(repo: Path, body: str) -> str:
    (repo / _RECORD).parent.mkdir(parents=True, exist_ok=True)
    (repo / _RECORD).write_text(body, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "c")
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def test_the_base_read_flags_a_key_added_in_a_real_git_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fails if the guard stopped reading the base (e.g. compared the record with itself)."""
    make_repo(tmp_path)
    first = _commit_record(tmp_path, f'{_NAME} = {{"alpha": ({{"a_test.py"}}, "why")}}\n')
    now_src = f'{_NAME} = {{"alpha": ({{"a_test.py"}}, "why"), "beta": ({{"b_test.py"}}, "why")}}\n'
    _commit_record(tmp_path, now_src)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("AUTOBOT_RATCHET_BASE_SHA", first)
    assert grown_against_base(tmp_path, literal_in(now_src, _NAME)) == {"beta": ["b_test.py"]}  # type: ignore[arg-type]


def test_a_planted_added_glob_key_is_caught() -> None:
    base = {"alpha": ({"a_test.py"}, "why")}
    now = {**base, "beta": ({"b_test.py"}, "why")}
    assert grown_entries(now, base) == {"beta": ["b_test.py"]}
    assert "dedicated workflow" in _complaint(grown_entries(now, base))
    assert grown_entries({**base, "beta": (set(), "why")}, base) == {"beta": []}, "an empty new key is a key"


def test_a_planted_added_guard_under_an_existing_key_is_caught() -> None:
    base = {"alpha": ({"a_test.py"}, "why")}
    now = {"alpha": ({"a_test.py", "b_test.py"}, "why")}
    assert grown_entries(now, base) == {"alpha": ["b_test.py"]}


def test_a_planted_removal_passes() -> None:
    base = {"alpha": ({"a_test.py", "b_test.py"}, "why"), "gamma": ({"c_test.py"}, "why")}
    assert grown_entries({"alpha": ({"a_test.py"}, "why")}, base) == {}
    assert grown_entries(base, base) == {}


def test_a_missing_base_record_reads_every_entry_as_added() -> None:
    assert set(grown_entries(GLOB_DECLARED_UNCOVERED, {})) == set(GLOB_DECLARED_UNCOVERED)


def _pin_base(repo: Path, monkeypatch: pytest.MonkeyPatch, body: str | None) -> None:
    """Make *repo*'s base commit hold the record *body*, or no record at all when None."""
    make_repo(repo)
    if body is None:
        (repo / "other.txt").write_text("x\n", encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "base without the record")
        base = git(repo, "rev-parse", "HEAD").stdout.strip()
    else:
        base = _commit_record(repo, body)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("AUTOBOT_RATCHET_BASE_SHA", base)


def test_a_record_absent_from_the_base_commit_fails_the_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard's own read, not just ``grown_entries({})``: no record at the base means every key is added."""
    _pin_base(tmp_path, monkeypatch, None)
    grown = grown_against_base(tmp_path, GLOB_DECLARED_UNCOVERED)
    assert set(grown) == set(GLOB_DECLARED_UNCOVERED), "a missing base record must read every key as added"


def test_an_empty_base_and_an_empty_record_pass() -> None:
    """The paid-off end state: nothing in the base, nothing now, nothing grew."""
    assert grown_entries({}, {}) == {}


def test_an_empty_base_record_in_a_real_git_history_passes_when_nothing_is_added(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pin_base(tmp_path, monkeypatch, f"{_NAME} = {{}}\n")
    assert _base_record(tmp_path) == {}
    assert grown_against_base(tmp_path, {}) == {}


def test_an_empty_base_record_still_flags_every_key_added_after_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not vacuous: dropping the truthiness check must not let additions to an empty record through."""
    _pin_base(tmp_path, monkeypatch, f"{_NAME} = {{}}\n")
    now = {"alpha": ({"a_test.py"}, "why")}
    assert grown_against_base(tmp_path, now) == {"alpha": ["a_test.py"]}


def test_an_absent_base_record_passes_an_empty_current_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _pin_base(tmp_path, monkeypatch, None)
    assert _base_record(tmp_path) == {}
    assert grown_against_base(tmp_path, {}) == {}


def test_the_live_check_passes_on_a_paid_off_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reach included: an empty record and an empty base is the end state, and it must not fail a floor."""
    _pin_base(tmp_path, monkeypatch, f"{_NAME} = {{}}\n")
    assert REACH.examined(tmp_path) == [_RECORD]
    check_record(tmp_path, {})


@pytest.mark.parametrize(
    "body",
    [None, f"{_NAME} = {{\n", "OTHER = {}\n", f"{_NAME} = ['not', 'a', 'dict']\n"],
    ids=["file-missing", "unparseable", "assignment-absent", "not-a-dict"],
)
def test_the_live_check_fails_when_the_record_was_not_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str | None
) -> None:
    """Non-vacuity: a record that cannot be read fails the reach even though nothing grew."""
    _pin_base(tmp_path, monkeypatch, body)
    assert REACH.population(tmp_path) == []
    with pytest.raises(ReachFloorError, match="reached 0"):
        check_record(tmp_path, {})
