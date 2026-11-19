# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An index-only revision is observable to the probe ladder, so adoption RUNS it (#20992, #17038).

``20261119_116`` creates two partial unique indexes and no table or column. Unobservable, a bracket ending
at ``20261118_115`` was advanced through the data-only tail and STAMPED head, so the indexes were never
built. No database needed: static facts against the real revision chain.
"""

from migrations.baseline import (
    INDEX_MARKERS,
    DbFacts,
    _script_directory,
    applied_status,
    extract_artifacts,
    find_candidate,
)

_REV = "20261119_116"
_PRIOR = "20261118_115"
_INDEXES = {idx for _t, idx in INDEX_MARKERS[_REV]}


def _statuses(facts: DbFacts) -> dict:
    script = _script_directory()
    artifacts = extract_artifacts(script)
    return script, {rev: applied_status(rev, artifacts, facts) for rev in artifacts}


def _facts(with_indexes: bool, table: bool = True) -> DbFacts:
    facts = DbFacts()
    if table:
        facts.tables.add("approvals")
    if with_indexes:
        facts.indexes = {("approvals", i) for i in _INDEXES}
    return facts


def test_the_revision_looks_absent_without_its_indexes_and_applied_with_them():
    artifacts = extract_artifacts(_script_directory())
    assert applied_status(_REV, artifacts, _facts(with_indexes=False)) is False
    assert applied_status(_REV, artifacts, _facts(with_indexes=True)) is True


def test_one_index_of_two_is_partial_not_applied():
    facts = _facts(with_indexes=False)
    facts.indexes = {("approvals", sorted(_INDEXES)[0])}
    assert applied_status(_REV, extract_artifacts(_script_directory()), facts) == "partial"


def test_without_the_approvals_table_the_revision_stays_unobservable():
    assert applied_status(_REV, extract_artifacts(_script_directory()), _facts(False, table=False)) is None


def test_adoption_does_not_stamp_head_over_missing_indexes():
    """The bug: a candidate at 115 was advanced to head across the 'data-only' 116, never creating it."""
    script, statuses = _statuses(_facts(with_indexes=False))
    for ancestor in {s.revision for s in script.iterate_revisions(_PRIOR, "base")}:
        statuses[ancestor] = True  # every earlier revision looks applied: the schema is "at 115"
    statuses[_REV] = applied_status(_REV, extract_artifacts(script), _facts(with_indexes=False))
    candidate = find_candidate(script, statuses)
    assert candidate == _PRIOR, f"expected adoption to stop at {_PRIOR} so 116 runs, got {candidate}"
