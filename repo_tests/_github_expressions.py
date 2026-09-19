# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A minimal evaluator for GitHub Actions' ``${{ }}`` expression syntax (#16931 review).

The trailer gate's `fetch-depth` is chosen by an expression, not a literal:
``(github.event_name == 'merge_group' || github.event.pull_request.commits > 90) && '0' || '100'``.
Nothing exercised that expression -- an off-by-one (``>=`` for ``>``), a wrong
field name, or a string-vs-number literal would go unnoticed by every existing
guard on this workflow (#16932 review). Pinning the expression's *text* would
not catch any of those, since the text would simply change along with the bug.

This module evaluates the real fragment instead: parse it, walk it against a
context dict shaped like GitHub's own `github` object, and return the value it
actually produces -- including GitHub's JS-style short-circuiting, where `&&`
and `||` return an *operand*, not a boolean (`'x' && '0'` is ``'0'``, not
``True``). Reimplementing that loosely (e.g. coercing to Python bool) would
silently pass a mutant that this workflow's own logic depends on: the `'0'`
string is truthy specifically *because* GitHub does not fold it to a number.

Scope is deliberately the fragment this one workflow needs: string/number
literals, ``==``, ``>``, ``>=``, ``&&``, ``||``, parentheses, and dotted
context lookups where a missing segment is null. Add operators only when a
real expression needs them -- this is an anchor for one gate, not a GitHub
Actions expression engine.
"""

from __future__ import annotations

import re

__all__ = ["evaluate", "strip_expression_braces"]

_TOKEN_PATTERN = re.compile(
    r"""
      (?P<ws>\s+)
    | (?P<op>==|>=|&&|\|\||>|\(|\))
    | (?P<string>'(?:[^']|'')*')
    | (?P<number>-?\d+(?:\.\d+)?)
    | (?P<ident>[A-Za-z_][A-Za-z0-9_.]*)
    """,
    re.VERBOSE,
)


def strip_expression_braces(raw: str) -> str:
    """Return the inner text of a ``${{ ... }}`` wrapper; raise if it is not one.

    Raising rather than returning the raw text unchanged means a workflow edit
    that drops the wrapper (e.g. hardcodes a literal) fails loudly here instead
    of silently evaluating whatever text was left.
    """
    match = re.fullmatch(r"\$\{\{\s*(.*?)\s*\}\}", raw.strip())
    if not match:
        raise ValueError(f"not a GitHub expression wrapper: {raw!r}")
    return match.group(1)


def _tokenize(expr: str) -> list[tuple[str, str]]:
    """Split an expression into ``(kind, text)`` tokens; reject unrecognized text.

    A gap between consecutive matches (rather than looping on ``.match`` at a
    cursor) would silently skip characters `finditer` could not match -- this
    walks the match positions and fails on any gap instead.
    """
    tokens: list[tuple[str, str]] = []
    pos = 0
    for match in _TOKEN_PATTERN.finditer(expr):
        if match.start() != pos:
            raise ValueError(
                f"unrecognized text at {pos} in {expr!r}: {expr[pos : match.start()]!r}"
            )
        pos = match.end()
        if match.lastgroup != "ws":
            tokens.append((match.lastgroup, match.group()))
    if pos != len(expr):
        raise ValueError(f"trailing unparsed text in {expr!r}: {expr[pos:]!r}")
    return tokens


def _lookup(context: dict, path: str) -> object:
    """Dotted context lookup. A missing segment anywhere returns null (``None``)."""
    value: object = context
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _truthy(value: object) -> bool:
    """GitHub's boolean coercion: null/false/0/'' are falsy, everything else is truthy.

    Order matters: ``bool`` is a subclass of ``int`` in Python, so the bool
    check must come first or ``False`` would fall into the numeric branch by
    coincidence rather than by this function's own rule.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value != ""
    return True


def _compare(op: str, left: object, right: object) -> bool:
    """Evaluate ``==`` / ``>`` / ``>=``. A null operand compares false to anything."""
    if left is None or right is None:
        return False
    if op == "==":
        return left == right
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    raise ValueError(f"unsupported operator {op!r}")


class _Parser:
    """Recursive-descent parser over ``||`` / ``&&`` / comparison / primary.

    That is GitHub's own precedence for this subset (loosest to tightest):
    ``||``, then ``&&``, then the comparison operators, then literals/lookups/
    parens.
    """

    def __init__(self, tokens: list[tuple[str, str]], context: dict) -> None:
        self._tokens = tokens
        self._pos = 0
        self._context = context

    def parse(self) -> object:
        value = self._or()
        if self._pos != len(self._tokens):
            raise ValueError(f"trailing tokens: {self._tokens[self._pos :]!r}")
        return value

    def _peek_op(self, *ops: str) -> bool:
        if self._pos >= len(self._tokens):
            return False
        kind, text = self._tokens[self._pos]
        return kind == "op" and text in ops

    def _or(self) -> object:
        """``A || B``: GitHub returns ``A`` if truthy, else ``B`` -- not a boolean."""
        value = self._and()
        while self._peek_op("||"):
            self._pos += 1
            rhs = self._and()
            value = value if _truthy(value) else rhs
        return value

    def _and(self) -> object:
        """``A && B``: GitHub returns ``A`` if falsy, else ``B`` -- not a boolean."""
        value = self._cmp()
        while self._peek_op("&&"):
            self._pos += 1
            rhs = self._cmp()
            value = rhs if _truthy(value) else value
        return value

    def _cmp(self) -> object:
        value = self._primary()
        if self._peek_op("==", ">", ">="):
            op = self._tokens[self._pos][1]
            self._pos += 1
            value = _compare(op, value, self._primary())
        return value

    def _primary(self) -> object:
        kind, text = self._tokens[self._pos]
        self._pos += 1
        if kind == "op" and text == "(":
            return self._parenthesized()
        if kind == "string":
            return text[1:-1].replace("''", "'")
        if kind == "number":
            return float(text) if "." in text else int(text)
        if kind == "ident":
            return _lookup(self._context, text)
        raise ValueError(f"unexpected token ({kind!r}, {text!r})")

    def _parenthesized(self) -> object:
        value = self._or()
        if not self._peek_op(")"):
            raise ValueError("unbalanced parentheses")
        self._pos += 1
        return value


def evaluate(expr: str, context: dict) -> object:
    """Evaluate a GitHub-expression fragment (no ``${{ }}`` wrapper) against a context dict."""
    return _Parser(_tokenize(expr), context).parse()
