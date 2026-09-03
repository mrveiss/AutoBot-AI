# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The twelve row conventions this backlog actually uses (#15439).

Every row below is copied from a live umbrella body, not invented -- #15357,
#12262, #13707, #13892, #13096 and #14774 between them cover every shape the
parser has to survive. A case set written from imagination would have agreed
with the naive reader that mis-parented 11 issues, because the shapes that break
it are the ones nobody would think to invent.

The pairs that matter are adjacent on purpose:

* ``1.1 (#11527)`` owns and ``No regression ... (#13884)`` does not -- identical
  punctuation, opposite meaning, separated only by the preceding clause.
* ``depends on: #13250`` and ``tracked as #15162`` are both preceded by a
  dependency phrase, and only the second is ownership.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from child_ref import blockers, child_ref  # noqa: E402

# (row, owned issue) -- the twelve conventions, each with its source umbrella.
ROWS = [
    # 1. #12262 -- leading reference, em-dash clauses after it.
    ("- [ ] #12264 — patch chromadb — 3 open Dependabot alert(s)", 12264),
    # 2. #13707 -- leading reference with a trailing dependency clause.
    (
        "- [ ] #13709 — approval-memory scope key generalisation · "
        "*depends on: #13250*",
        13709,
    ),
    # 3. #13707 -- several blockers, none of them the child.
    (
        "- [ ] #13714 — `MailboxView.vue` read/compose GUI, 11 locales · "
        "*depends on: #13712, #13710*",
        13714,
    ),
    # 4. #13096 -- a bold outline label before the reference.
    (
        "- [ ] **A1** #13097 — Agent cancel/timeout orphans the whole "
        "subprocess tree *(live bug, P0)*",
        13097,
    ),
    # 5. #15357 -- the reference trails the task description after a separator.
    (
        "- [ ] Task 1: Scope `enforce-precommit` to the PR diff instead of "
        "`--all-files` — #15358 (−21 min)",
        15358,
    ),
    # 6. #13892 -- the row names the PR that carries it; a PR is not a child.
    (
        "- [ ] #13894 — KB upload loses page provenance; facts cannot cite a "
        "source page — PR #14239 open",
        13894,
    ),
    # 7. #13892 -- a PR *and* a sibling split out of it, neither owned.
    (
        "- [ ] #13895 — `_extract_pdf_tables` stub returns `[]` while the "
        "result claims `confidence: 0.95` — PR #14233 open; real pdfplumber "
        "extraction split out as #14232",
        13895,
    ),
    # 8. #13096 -- an epic whose own sub-tree is a range, not this row's children.
    (
        "- [ ] **V5** #13110 — **Vision epic** (own sub-tree: #13119-#13123) — "
        "capture exists in isolation",
        13110,
    ),
    # 9. #14774 -- an outline number and a parenthesised reference: owned.
    ("- [x] 1.1 (#11527) Add stylelint", 11527),
    # 10. #14774 -- prose and a parenthesised reference: an acceptance criterion.
    ("- [ ] No regression to the instrumentation (#13884)", None),
    # 11. #15357 -- `tracked as` outranks the `depends on` earlier in the row.
    (
        "- [ ] Task 5: retire the shim once Task 1 lands — depends on Task 1 - "
        "tracked as #15162",
        15162,
    ),
    # 12. Prose that mentions an issue is not a checklist row at all.
    ("Related: #13251 gates every retrieval-tuning issue in the backlog", None),
]


@pytest.mark.parametrize("row,owned", ROWS, ids=[str(i + 1) for i in range(len(ROWS))])
def test_child_ref_reads_the_owned_issue(row: str, owned: int | None) -> None:
    assert child_ref(row) == owned


def test_a_pull_request_reference_is_never_a_child() -> None:
    """The closing PR shares the row with the issue it closes."""
    assert child_ref("- [ ] #13894 — done — PR #14239 open") == 13894


def test_a_sub_tree_range_is_not_flattened_into_this_row() -> None:
    """#13119-#13123 belong to #13110, not to the umbrella listing it."""
    row = "- [ ] **V5** #13110 — **Vision epic** (own sub-tree: #13119-#13123)"
    assert child_ref(row) == 13110


def test_blockers_are_read_without_becoming_children() -> None:
    row = (
        "- [ ] #13714 — `MailboxView.vue` read/compose GUI, 11 locales · "
        "*depends on: #13712, #13710*"
    )
    assert child_ref(row) == 13714
    assert blockers(row) == [13712, 13710]


def test_a_row_with_no_dependency_clause_declares_no_blockers() -> None:
    row = "- [ ] #13708 — content-scanning credential redactor · *depends on: nothing* ·"
    assert child_ref(row) == 13708
    assert blockers(row) == []


def test_ownership_and_dependency_are_separate_graphs() -> None:
    """Neither function may consume the other's references."""
    row = "- [ ] #13712 — mail connector under `knowledge/connectors/` · *depends on: #13708*"
    assert child_ref(row) == 13712
    assert blockers(row) == [13708]
    assert child_ref(row) not in blockers(row)
