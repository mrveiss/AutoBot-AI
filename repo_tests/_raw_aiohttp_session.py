# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AST detector for raw ``aiohttp.ClientSession(...)`` constructions (#12979).

Separate from the guard that consumes it, deliberately. A detector that holds
its own corpus invites the fix that makes the test pass; split, editing the
matcher and editing what it must catch are two files in one diff
(``MEASUREMENT_DISCIPLINE.md``, "a detector built from what was found inherits
its vocabulary").

**Why AST and not grep.** The string ``aiohttp.ClientSession(`` appears in this
repository in docstrings, emitted log strings and a code-generator replacement
template as well as in code. Measured on ``origin/main`` at ``0a4cffced``:
``git grep -c`` over tracked ``*.py`` reads **115** occurrences in **70**
files, while this walker reads **99** constructions in **61** files. The 16
extra are prose. A text guard set from the larger number buys silent slack for
sixteen future raw sessions, and a text guard is *satisfied* by a comment
carrying the same string — which is the specific failure this module exists
not to have.

Nothing here reads the repository or decides anything. The two questions a
caller asks are kept apart on purpose:

- :func:`client_session_sites` takes **source text** and returns the sites in
  it, so it can be handed a fixture that is not in the tree.
- :func:`scan_paths` takes a root and an explicit file list, so the population
  being swept is the caller's declared decision rather than a glob buried here.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable, NamedTuple

__all__ = ["Site", "client_session_sites", "scan_paths"]


class Site(NamedTuple):
    """One ``ClientSession(...)`` construction.

    Attributes
    ----------
    lineno:
        1-based line of the call expression.
    bound:
        ``True`` when the call is **not** the direct operand of an
        ``async with`` item — i.e. the session is stored (``self._session =
        aiohttp.ClientSession(...)``) and therefore outlives the statement.
        ``False`` is the per-request shape ``async with
        aiohttp.ClientSession() as s:`` that #12979 is about. This is a
        structural fact, not a judgement: a stored session may still be a
        defect, but it is never the per-request defect.
    keywords:
        Keyword argument names passed to the call, in source order. The one
        that matters is ``connector`` — an SSRF-pinned or custom-TLS connector
        is a *session*-level object the pooled client cannot accept per
        request, so those sites cannot be converted without reopening #12278.
    """

    lineno: int
    bound: bool
    keywords: tuple[str, ...]


def _with_operands(tree: ast.AST) -> set[int]:
    """``id()`` of every expression used directly as a ``with``-item operand."""
    operands: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                operands.add(id(item.context_expr))
    return operands


def _is_client_session_call(func: ast.expr) -> bool:
    """True for ``<anything>.ClientSession`` and for a bare ``ClientSession``.

    Deliberately NOT keyed on the receiver being the name ``aiohttp``. The
    alias is free (``import aiohttp as http``), the symbol is importable
    directly (``from aiohttp import ClientSession``), and a matcher that
    enumerates the spellings already in the tree reports a confident zero over
    every spelling nobody thought of. The cost of the wider net is that a
    same-named class from another library would be counted; no such class is
    constructed anywhere in this tree, and over-counting produces a red that
    names its file, which is the cheap direction to be wrong in.
    """
    if isinstance(func, ast.Attribute):
        return func.attr == "ClientSession"
    return isinstance(func, ast.Name) and func.id == "ClientSession"


def client_session_sites(source: str) -> tuple[Site, ...]:
    """Every ``ClientSession(...)`` construction in *source*.

    Raises ``SyntaxError`` rather than returning ``()`` for unparsable source:
    an empty result from a parser that choked is indistinguishable from a
    clean file, and the caller must be the one to decide what that means.
    """
    tree = ast.parse(source)
    operands = _with_operands(tree)
    sites = [
        Site(
            lineno=node.lineno,
            bound=id(node) not in operands,
            keywords=tuple(kw.arg for kw in node.keywords if kw.arg),
        )
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _is_client_session_call(node.func)
    ]
    return tuple(sorted(sites))


def scan_paths(root: Path, relative_paths: Iterable[str]) -> dict[str, tuple[Site, ...]]:
    """Map each repo-relative path in *relative_paths* that has sites to them.

    Files that fail to parse are reported with an empty tuple under a key
    suffixed ``" (UNPARSED)"`` so a parse failure can never be read as a clean
    file by the caller's set comparison.
    """
    found: dict[str, tuple[Site, ...]] = {}
    for rel in relative_paths:
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        if "ClientSession" not in text:
            # A pure speed gate on the symbol name, not a matcher: anything it
            # skips cannot contain a call to something spelled ClientSession.
            continue
        try:
            sites = client_session_sites(text)
        except SyntaxError:
            found[f"{rel} (UNPARSED)"] = ()
            continue
        if sites:
            found[rel] = sites
    return found
