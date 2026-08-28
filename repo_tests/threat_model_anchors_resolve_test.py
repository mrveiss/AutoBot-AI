# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every anchor in THREAT_MODEL.md must still point at real code (#15217).

`docs/developer/THREAT_MODEL.md` is read at the start of a security review to
supply the trust boundary and canonical enforcement point for four subsystems.
Its value is entirely in those `file:line` citations: a reviewer who follows a
stale one lands on unrelated code and concludes the invariant is gone — or,
worse, that it is intact somewhere it is not.

Line numbers rot on the very refactors a security review is most needed for, and
they rot **silently**: nothing else in the repo reads this file. This derives the
citations from the document itself, so an anchor added later is covered without
anyone remembering to extend this test.

Anchor grammar (one form, deliberately):

    [`label`](../../relative/path.py)      sets the current file
    `symbol` (:NNN)                        asserts *symbol* is on line NNN of it
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOC = REPO_ROOT / "docs" / "developer" / "THREAT_MODEL.md"

_LINK_RE = re.compile(r"\[[^\]]+\]\((\.\./[^)\s]+)\)")
_ANCHOR_RE = re.compile(r"`([^`]+)`\s*\(:(\d+)\)")
# A citation is only as good as the symbol name it carries; strip the doc's
# prose decoration ("a.b" -> "b") down to the identifier that must be present.
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _doc_text() -> str:
    assert DOC.is_file(), f"{DOC} is missing — the secreview skill links to it"
    return DOC.read_text(encoding="utf-8")


def _links() -> list[str]:
    return _LINK_RE.findall(_doc_text())


def _anchors() -> list[tuple[str, str, int]]:
    """Return ``(relative_path, symbol, line)`` for every citation, in order."""
    found: list[tuple[str, str, int]] = []
    current: str | None = None
    for line in _doc_text().splitlines():
        # A link may share a line with the anchors it introduces, so scan the
        # links first and let the last one become current for that whole line.
        # Taking the *first* match would misattribute anchors that follow a
        # second link on the same line — silently, and in the passing direction.
        links = _LINK_RE.findall(line)
        if links:
            current = links[-1]
        for symbol, lineno in _ANCHOR_RE.findall(line):
            assert current, f"anchor `{symbol}` (:{lineno}) has no preceding file link"
            found.append((current, symbol, int(lineno)))
    return found


def test_document_exists_and_is_short_enough_to_read_every_review():
    # The whole premise is that it is cheaper to read than to re-derive.
    assert len(_doc_text().splitlines()) <= 140


def test_every_relative_link_resolves():
    broken = [rel for rel in _links() if not (DOC.parent / rel).resolve().is_file()]
    assert not broken, f"broken links in THREAT_MODEL.md: {broken}"


def test_anchors_were_actually_parsed():
    # A regex that silently matches nothing would make every check below pass.
    anchors = _anchors()
    assert len(anchors) >= 25, f"only {len(anchors)} anchors parsed — grammar drifted"


@pytest.mark.parametrize("rel,symbol,lineno", _anchors(), ids=lambda v: str(v))
def test_anchor_points_at_its_symbol(rel: str, symbol: str, lineno: int):
    target = (DOC.parent / rel).resolve()
    assert target.is_file(), f"{rel} does not exist"
    lines = target.read_text(encoding="utf-8").splitlines()
    assert lineno <= len(lines), f"{rel}:{lineno} is past end of file ({len(lines)} lines)"

    ident = _IDENT_RE.findall(symbol)[-1]
    actual = lines[lineno - 1]
    # Word-boundary, not substring: a comment or unrelated string that merely
    # contains the identifier would otherwise pass for a definition that moved.
    assert re.search(rf"\b{re.escape(ident)}\b", actual), (
        f"THREAT_MODEL.md cites `{symbol}` at {rel}:{lineno}, "
        f"but that line reads: {actual.strip()!r}"
    )
