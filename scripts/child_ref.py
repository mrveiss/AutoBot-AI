# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Read an umbrella checklist row into the one issue it owns (#15439).

An umbrella states its children as a markdown checklist, and the naive reader --
*every ``#N`` on the line is a child* -- mis-parented 11 issues. A row routinely
carries several references that are **not** children: the pull request that
closed it, a blocker it waits on, a sibling it was split out of, and an epic's
own sub-range. Attaching those as sub-issues corrupts the hierarchy in a way
that reads as data rather than as an error.

Ownership is decided by the clause immediately before the reference:

===============================================================  =============
row                                                              owns
===============================================================  =============
``- [ ] #12264 - patch chromadb - 3 open Dependabot alert(s)``   ``12264``
``- [x] 1.1 (#11527) Add stylelint``                             ``11527``
``- [ ] **A1** #13097 - Agent cancel orphans the tree``          ``13097``
``- [ ] Task 1: Scope enforce-precommit to the diff - #15358``   ``15358``
``- [ ] ... depends on Task 1 - tracked as #15162``              ``15162``
``- [ ] No regression to the instrumentation (#13884)``          nothing
``- [ ] #13894 - KB upload loses provenance - PR #14239 open``   ``13894``
``- [ ] #13709 - scope key generalisation - depends on: #13250`` ``13709``
===============================================================  =============

The distinction between rows two and six is the whole difficulty: both end in a
parenthesised reference, and only the *preceding clause* separates a numbered
task from an acceptance criterion that happens to cite an issue.

``blocked_by`` is a separate graph and is never expressed through ownership --
:func:`blockers` reads it from the same row without either function consuming
the other's references.
"""

from __future__ import annotations

import re
from typing import List, Optional

# A row owns a child only if it is a checklist row. Prose that mentions an issue
# is not a claim of ownership, and treating it as one is how #15444's nine
# mis-parented issues were created.
_CHECKBOX = re.compile(r"^\s*[-*]\s*\[[ xX]\]\s*")

_REF = re.compile(r"#(\d+)")

# Clause separators, in the four styles this backlog actually uses. An em dash
# and a middot are the common ones; ``: `` closes a "Task 1:" label.
_SEPARATOR_TAIL = re.compile(r"(?:[—–·]|\s-\s|:)\s*$")

# ``tracked as #N`` is an ownership marker and deliberately outranks a
# ``depends on`` earlier in the same row -- a row may say what it waits for and
# then name the issue that carries it.
_TRACKED_AS_TAIL = re.compile(r"\btracked as\s*$", re.IGNORECASE)

# Everything that makes a reference *not* a child, checked against the text
# immediately preceding it.
_PR_TAIL = re.compile(r"\bPR\s*$", re.IGNORECASE)
_RANGE_TAIL = re.compile(r"#\d+\s*[-–—]\s*$")
_SIBLING_TAIL = re.compile(
    r"\b(?:split (?:out )?(?:as|to|into)|superseded by|supersedes|see|closes|"
    r"closed by|fixed by|duplicate of|related(?: to)?|follow-?up(?: to)?)"
    r"[:\s]*$",
    re.IGNORECASE,
)

# ``depends on: #A, #B`` -- the blocker list. Consumed by blockers(), never by
# child_ref(). The list may be comma separated and may carry emphasis markers.
_DEPENDS_ON = re.compile(r"\bdepends on\b[:\s]*(?P<refs>[^·—\n]*)", re.IGNORECASE)

# A leading label: nothing at all, a bold tag such as ``**A1**``, or an outline
# number such as ``1.1``. Anything longer is prose, and prose before a reference
# means the row is describing rather than owning.
_LABEL_ONLY = re.compile(r"[A-Z]{0,3}\d+(?:\.\d+)*[.:)\]]?")


def _strip_decoration(text: str) -> str:
    """Remove markdown emphasis and opening brackets so a label can be seen."""
    return re.sub(r"[*_`(\[]", "", text).strip()


def _is_label_prefix(prefix: str) -> bool:
    """True when nothing but a task label stands between the row and the ref."""
    bare = _strip_decoration(prefix)
    if not bare:
        return True
    return bool(_LABEL_ONLY.fullmatch(bare))


def _disqualified(prefix: str) -> bool:
    """True when the preceding clause makes this reference someone else's."""
    return bool(
        _PR_TAIL.search(prefix)
        or _RANGE_TAIL.search(prefix)
        or _SIBLING_TAIL.search(prefix)
    )


def _depends_on_spans(body: str) -> List[range]:
    """Character ranges covered by a ``depends on`` clause."""
    return [range(m.start("refs"), m.end("refs")) for m in _DEPENDS_ON.finditer(body)]


def child_ref(row: str) -> Optional[int]:
    """Return the issue number this checklist row owns, or ``None``.

    Returns at most one issue: a row owns a single child by construction, and a
    reader that returns several has stopped distinguishing ownership from
    mention.
    """
    checkbox = _CHECKBOX.match(row)
    if checkbox is None:
        return None
    body = row[checkbox.end() :]
    blocker_spans = _depends_on_spans(body)

    for match in _REF.finditer(body):
        prefix = body[: match.start()]
        if _disqualified(prefix):
            continue
        # A reference inside a ``depends on`` clause is a blocker, and a blocker
        # is never a child. ``tracked as`` is checked first so it can outrank an
        # earlier ``depends on`` in the same row.
        if _TRACKED_AS_TAIL.search(prefix):
            return int(match.group(1))
        if any(match.start() in span for span in blocker_spans):
            continue
        if _is_label_prefix(prefix):
            return int(match.group(1))
        if _SEPARATOR_TAIL.search(prefix) and match.end() >= _last_ref_end(body):
            return int(match.group(1))
    return None


def _last_ref_end(body: str) -> int:
    """End offset of the final reference in the row, or ``-1`` when there is none."""
    end = -1
    for match in _REF.finditer(body):
        end = match.end()
    return end


def blockers(row: str) -> List[int]:
    """Return the issues this row declares it waits on.

    Separate graph, separate function. Hierarchy and dependencies are never used
    to express one another, so a caller that wants both asks for both.
    """
    found: List[int] = []
    for clause in _DEPENDS_ON.finditer(row):
        for match in _REF.finditer(clause.group("refs")):
            number = int(match.group(1))
            if number not in found:
                found.append(number)
    return found
