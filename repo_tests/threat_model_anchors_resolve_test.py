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

import ast
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


def _format_lines(lines: list[int]) -> str:
    """`31`, or `31, 47 or 63` — the actual locations, not just a complaint."""
    if len(lines) == 1:
        return str(lines[0])
    return ", ".join(str(n) for n in lines[:-1]) + f" or {lines[-1]}"


def _parse(target: Path) -> ast.Module | None:
    try:
        return ast.parse(target.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):  # pragma: no cover - a tracked file that will not parse
        return None


def _definition_lines(target: Path, ident: str) -> list[int]:
    """Every line where *ident* is defined: def, class, or module/class assignment."""
    tree = _parse(target)
    if tree is None:
        return []
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == ident:
            found.add(node.lineno)
        elif isinstance(node, ast.Assign):
            for target_node in node.targets:
                if isinstance(target_node, ast.Name) and target_node.id == ident:
                    found.add(target_node.lineno)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == ident:
            found.add(node.target.lineno)
    return sorted(found)


def _reference_lines(target: Path, ident: str) -> list[int]:
    """Lines where *ident* appears as code — a name or an attribute access.

    Not a text search: a mention inside a comment or a docstring is not a
    reference, and treating one as a citation is how an anchor survives the
    thing it pointed at being deleted.
    """
    tree = _parse(target)
    if tree is None:
        return []
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == ident:
            found.add(node.lineno)
        elif isinstance(node, ast.Attribute) and node.attr == ident:
            found.add(node.lineno)
        elif isinstance(node, ast.alias) and (node.asname or node.name).split(".")[-1] == ident:
            found.add(getattr(node, "lineno", 0) or 0)
    found.discard(0)
    return sorted(found)


@pytest.mark.parametrize("rel,symbol,lineno", _anchors(), ids=lambda v: str(v))
def test_anchor_points_at_its_symbol(rel: str, symbol: str, lineno: int):
    target = (DOC.parent / rel).resolve()
    assert target.is_file(), f"{rel} does not exist"
    lines = target.read_text(encoding="utf-8").splitlines()
    assert lineno <= len(lines), f"{rel}:{lineno} is past end of file ({len(lines)} lines)"

    ident = _IDENT_RE.findall(symbol)[-1]
    actual = lines[lineno - 1]

    # #15247: parse the file rather than regex the cited line. A word-boundary
    # match on one line accepts a comment or a docstring that merely mentions the
    # identifier, and — worse — when a definition moves it can only say "that
    # line reads X". It cannot say where the symbol went, which is the one fact
    # someone fixing the anchor needs.
    definitions = _definition_lines(target, ident)

    if definitions:
        assert lineno in definitions, (
            f"THREAT_MODEL.md cites `{symbol}` at {rel}:{lineno}, but {ident} is "
            f"defined at {rel}:{_format_lines(definitions)}. Update the anchor to "
            f"the line above; the cited line reads: {actual.strip()!r}"
        )
        return

    # No definition in this file: the doc legitimately anchors call sites too
    # (`import_module` and `spec_from_file_location` in the plugin loader are
    # stdlib calls, not definitions here). Require the identifier to appear as
    # real code on that line — a Name or an attribute — so a mention in a comment
    # or string still fails, which the regex could not distinguish.
    uses = _reference_lines(target, ident)
    assert uses, (
        f"THREAT_MODEL.md cites `{symbol}` in {rel}, but {ident} appears there "
        f"neither as a definition nor as a code reference — the file link is stale"
    )
    assert lineno in uses, (
        f"THREAT_MODEL.md cites `{symbol}` at {rel}:{lineno}, but {ident} is used "
        f"at {rel}:{_format_lines(uses)}. The cited line reads: {actual.strip()!r}"
    )
