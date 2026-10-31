# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Find hand-rolled date formatters by what they do, not what they are called (#20004).

``frontend_local_date_formatter_ratchet_19905_test.py`` counted declarations named ``formatDate``
and the like, so ``renderStamp`` or ``fmt`` with the same ``toLocaleString`` body went unseen.
A *local date formatter* here is a named local function (``function`` declaration, ``const`` bound
to an arrow or function expression, object/class method or property) whose own body -- nested
functions excluded, they are judged on their own -- formats through ``toLocale*String`` or
``Intl.DateTimeFormat``. The name never decides.
"""

from __future__ import annotations

import re

from tools.lint._comment_syntax import code_text

# ``toLocaleString`` is also how a number is grouped, so it counts only beside a ``Date``; the
# date-only methods and ``Intl.DateTimeFormat`` always count, except the call that merely asks
# which timezone the browser is in.
_DATE_ONLY = re.compile(
    r"\.toLocale(?:Date|Time)String\s*\(|\bIntl\s*\.\s*DateTimeFormat\b(?!\s*\(\s*\)\s*\.\s*resolvedOptions)"
)
_ANY = re.compile(r"\.toLocaleString\s*\(")
_DATE = re.compile(r"\bDate\b")
_MODS = r"(?:(?:public|private|protected|static|readonly|async)[ \t]+)*"
_NOT_METHODS = {"if", "for", "while", "switch", "catch", "function", "return", "with", "else", "do"}
_HEAD = re.compile(
    rf"^[ \t]*(?:export[ \t]+(?:default[ \t]+)?)?(?:"
    rf"(?:async[ \t]+)?function[ \t]*\*?[ \t]*(?P<fn>[A-Za-z_$][\w$]*)\s*(?:<[^>(]*>)?\s*(?=\()"
    rf"|(?:const|let|var)[ \t]+(?P<var>[A-Za-z_$][\w$]*)\s*(?::[^\n=]*)?=\s*(?:async\s*)?(?:<[^>]*>\s*)?"
    rf"(?:(?P<fexpr>function\b[^(]*(?=\())|(?P<arrow1>[A-Za-z_$][\w$]*(?=\s*=>))|(?=\())"
    rf"|{_MODS}(?P<method>[A-Za-z_$][\w$]*)\s*(?:<[^>(]*>)?\s*(?=\()"
    rf"|{_MODS}(?P<prop>[A-Za-z_$][\w$]*)[ \t]*:\s*(?:async\s*)?(?:<[^>]*>\s*)?"
    rf"(?:(?P<pexpr>function\b[^(]*(?=\())|(?P<parrow1>[A-Za-z_$][\w$]*(?=\s*=>))|(?=\())"
    rf")",
    re.M,
)


def _skip_string(text: str, i: int) -> int:
    """Index just past the string or template literal that opens at ``i``."""
    quote, i = text[i], i + 1
    while i < len(text) and text[i] != quote:
        i += 2 if text[i] == "\\" else 1
    return i + 1


def _match_close(text: str, i: int) -> int:
    """Index just past the bracket that closes the one opening at ``i`` (``-1`` when unbalanced)."""
    depth = 0
    while i < len(text):
        c = text[i]
        if c in "'\"`":
            i = _skip_string(text, i)
            continue
        depth += c in "([{"
        depth -= c in ")]}"
        i += 1
        if depth == 0:
            return i
    return -1


def _expression_end(text: str, i: int) -> int:
    """End of an arrow's expression body: the first ``;`` or ``,`` or closer at depth 0."""
    while i < len(text):
        c = text[i]
        if c in "'\"`":
            i = _skip_string(text, i)
        elif c in "([{":
            close = _match_close(text, i)
            i = len(text) if close < 0 else close
        elif c in ";,)]}":
            return i
        elif c == "\n" and not re.match(r"\s*(?:[.?:+|&*/-]|\))", text[i + 1 :]):
            return i
        else:
            i += 1
    return i


def _after_params(text: str, i: int, arrow: bool) -> tuple[int, int] | None:
    """Body span for the parameter list opening at ``i``; ``None`` when it is not a function."""
    close = _match_close(text, i)
    if close < 0:
        return None
    tail = re.compile(r"\s*(?::[^=;{]*?)?=>\s*" if arrow else r"\s*(?::[^{;=]+)?(?=\{)").match(text, close)
    if tail is None:
        return None
    start = tail.end()
    if text.startswith("{", start):
        end = _match_close(text, start)
        return (start, len(text) if end < 0 else end)
    return (start, _expression_end(text, start)) if arrow else None


def _arrow_body(text: str, start: int) -> tuple[int, int]:
    """Body span of an arrow whose ``=>`` has just ended at ``start``."""
    start = start + len(text[start:]) - len(text[start:].lstrip())
    if text.startswith("{", start):
        end = _match_close(text, start)
        return (start, len(text) if end < 0 else end)
    return (start, _expression_end(text, start))


def _head_span(text: str, m: re.Match[str]) -> tuple[int, int] | None:
    """Span from the head ``m`` matched to the end of that function's body; ``None`` if not one."""
    bare = m.group("arrow1") or m.group("parrow1")
    if bare:
        tail = re.compile(r"\s*=>\s*").match(text, m.end())
        span = _arrow_body(text, tail.end()) if tail else None
    else:
        plain = bool(m.group("fn") or m.group("method") or m.group("fexpr") or m.group("pexpr"))
        span = _after_params(text, m.end(), arrow=not plain)
    return (m.start(), span[1]) if span else None


def _name(m: re.Match[str]) -> str:
    return next(m.group(k) for k in ("fn", "var", "method", "prop") if m.group(k))


def _spans(text: str) -> dict[tuple[int, int], str]:
    """Head-to-end span of every named local function in ``text``, with its name."""
    found = {}
    for m in _HEAD.finditer(text):
        if m.group("method") in _NOT_METHODS:
            continue
        if span := _head_span(text, m):
            found[span] = _name(m)
    return found


def _own_text(text: str, span: tuple[int, int], spans: list[tuple[int, int]]) -> str:
    """The function at ``span`` without the functions nested inside it."""
    lo, hi = span
    inner = [s for s in spans if lo < s[0] and s[1] <= hi]
    top = sorted(s for s in inner if not any(o != s and o[0] <= s[0] and s[1] <= o[1] for o in inner))
    own, pos = [], lo
    for ilo, ihi in top:
        own.append(text[pos:ilo])
        pos = ihi
    own.append(text[pos:hi])
    return "".join(own)


def _formats(own: str) -> bool:
    return bool(_DATE_ONLY.search(own) or (_ANY.search(own) and _DATE.search(own)))


def date_formatter_names(text: str) -> list[str]:
    """Names of the named local functions in ``text`` that format dates, whatever they are called."""
    text = code_text(text, name="source.ts", strip_trailing=True)
    named = _spans(text)
    spans = sorted(named)
    return [named[s] for s in spans if _formats(_own_text(text, s, spans))]
