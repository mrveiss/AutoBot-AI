# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""An index row must not claim a phase its own document contradicts (#17893).

``docs/research/_index.md`` summarises each research document, including how far the
analysis got. The row is written when the document is created and is not revisited when
the document grows, so the drift runs one way: **toward work looking less done than it
is**. The live instance was `private-tenant-chat-reference-app`, whose row read
"AutoBot comparison not started" while its document carried a completed
``## Phase 2 — AutoBot Comparison``.

Why this is worth a guard rather than a correction: the index is the entry point. A
reader deciding whether an analysis is worth continuing reads the row, not the document,
so a row saying "not started" against a finished Phase 2 sends someone to redo completed
work. That is a stale *record* producing a confident wrong answer in a correct reader --
the same shape as a stale acceptance criterion.

**Scope, stated because the obvious wider version is wrong.** This asserts one direction
only: a row claiming the comparison was never started, against a document that has the
section. The converse -- a row claiming Phase 2 while the document lacks the heading --
is NOT asserted, because a phase can be complete and recorded in prose under a different
heading, and a guard demanding one spelling would force the document to match the
checker rather than the reader. One direction is decidable from the text; the other is
not.

**The vocabulary is fixed here deliberately**, not matched loosely. A regex permissive
enough to catch any phrasing also matches the surrounding sentence -- this repository
has hit that repeatedly, most recently a detector that matched the comment documenting
it. If a row uses wording outside ``_NOT_STARTED``, this guard does not see it, and that
is a stated limit rather than a silent one.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root

#: Rows are ``| [[slug]] | prose |``. The slug resolves to ``docs/research/<slug>.md``.
_ROW = re.compile(r"^\|\s*\[\[([^\]]+)\]\]\s*\|(.*)$")

#: A row asserting the AutoBot comparison never happened. Fixed spellings, not a loose
#: pattern -- see the module docstring on why a permissive regex is the failure mode.
_NOT_STARTED = re.compile(
    r"comparison not started|Phase 1 source analysis only|source analysis only",
    re.IGNORECASE,
)

#: A row asserting it did. Checked so a row carrying BOTH is not read as "not started".
_STARTED = re.compile(r"Phase 2 (?:complete|done)|Phase 2 —|Phase 2:", re.IGNORECASE)

#: The heading a completed comparison writes.
_PHASE_2_HEADING = re.compile(r"^##\s+Phase 2\b", re.MULTILINE)

#: Reach floor. Resolving zero rows must fail rather than report no disagreements --
#: "nothing was read" and "nothing disagreed" produce the same empty result otherwise.
#: 40 against 44 resolvable today; it bounds a broken parse, not the population's growth.
_MIN_ROWS_RESOLVED = 40


def _index_path() -> Path:
    return repo_root() / "docs" / "research" / "_index.md"


def resolved_rows(index_text: str, docs_dir: Path) -> list[tuple[str, str, str]]:
    """``(slug, row prose, document text)`` for every row whose document exists.

    A row naming a document that is not there is skipped rather than failed: the index
    links out to work that may legitimately live elsewhere, and that is a different
    defect from the one this guard is about.
    """
    rows: list[tuple[str, str, str]] = []
    for line in index_text.splitlines():
        match = _ROW.match(line)
        if match is None:
            continue
        slug, prose = match.group(1), match.group(2)
        doc = docs_dir / f"{slug}.md"
        if not doc.is_file():
            continue
        rows.append((slug, prose, doc.read_text(encoding="utf-8")))
    return rows


def contradicted_rows(rows: list[tuple[str, str, str]]) -> list[str]:
    """Slugs whose row says the comparison never started while the document has it."""
    offenders: list[str] = []
    for slug, prose, text in rows:
        claims_none = bool(_NOT_STARTED.search(prose)) and not _STARTED.search(prose)
        if claims_none and _PHASE_2_HEADING.search(text):
            offenders.append(slug)
    return offenders


def test_the_index_resolves_a_population_worth_asserting_on() -> None:
    """Reach. A parse that matched nothing would otherwise report a clean tree."""
    rows = resolved_rows(_index_path().read_text(encoding="utf-8"), _index_path().parent)
    assert len(rows) >= _MIN_ROWS_RESOLVED, (
        f"only {len(rows)} index rows resolved to a document, below the floor of "
        f"{_MIN_ROWS_RESOLVED} -- the row pattern or the docs directory has moved, so "
        "a clean result below means nothing was read, not that nothing disagreed"
    )


def test_no_row_claims_a_phase_its_document_contradicts() -> None:
    """#17893: the live instance was a row reading 'not started' over a finished Phase 2."""
    rows = resolved_rows(_index_path().read_text(encoding="utf-8"), _index_path().parent)
    offenders = contradicted_rows(rows)
    assert not offenders, (
        "these index rows say the AutoBot comparison never started, but their documents "
        f"contain a '## Phase 2' section: {offenders}. The index is the entry point, so "
        "a row reading 'not started' over finished work sends the next reader to redo it."
    )


def test_a_row_contradicting_its_document_is_reported() -> None:
    """The detector fires. Without this, the clean result above licenses nothing."""
    rows = [("some-doc", "Phase 1 source analysis only", "# T\n\n## Phase 2 — AutoBot Comparison\n")]
    assert contradicted_rows(rows) == ["some-doc"]


def test_a_row_that_already_says_phase_2_is_not_reported() -> None:
    """The contrast: both markers present means the row is current, not contradictory."""
    rows = [("some-doc", "Phase 1 only. **Phase 2 complete:** five candidates", "## Phase 2 — x\n")]
    assert contradicted_rows(rows) == []


def test_a_not_started_row_whose_document_has_no_phase_2_is_not_reported() -> None:
    """The other contrast: an honestly unstarted analysis must not be flagged."""
    rows = [("some-doc", "Phase 1 source analysis only", "# T\n\n## Findings\n")]
    assert contradicted_rows(rows) == []
