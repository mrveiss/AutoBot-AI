# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Calls built through a same-file URL helper, judged by method and by literal segment (#21307).

``const uploadsUrl = (): string => `${getApiBase()}/knowledge_base/uploads` `` is ``/api`` + its template, so
``apiClient.get(`${uploadsUrl()}/${id}`)`` is ``GET /api/knowledge_base/uploads/{p}`` and a bare
``apiClient.rawRequest(uploadsUrl(), { method: 'POST' })`` is ``POST /api/knowledge_base/uploads``.

Unlike the verb-blind callers of ``_unconnected_routes._reached``, these connect a route only when

* the method is the route's (``get``/``post``/``put``/``patch``/``delete``; ``rawRequest``/``request`` read
  ``method: '...'`` from the call's options, default GET), and
* every call segment that is a placeholder meets a route PARAMETER: ``GET /uploads/${id}`` does not reach the
  literal route ``GET /uploads/expired``, which a router serves before ``/{id}``.

Only a call through a recognised client receiver counts (``console.log(`${h()}/x`)`` and ``fetch`` do not).

A helper declared in another file is followed in one case: the file declaring it IMPORTS the calling file and hands
the helper (and the client) in, so the call reads ``deps.api.get(`${deps.conversationApi()}/preview/${id}`)``
(#21307: the composable that builds the URL composes the one that calls it). The receiver and the helper are
then reached through one member access; a helper of a file that does not import the caller is not followed.
"""

from __future__ import annotations

import posixpath
import re

from repo_tests._unconnected_clients import _VERBS, prepared_text
from repo_tests._unconnected_common import Tree

#: ``const name = (args)[: string] =>`` then a ``${getApiBase()}/...`` template: a URL helper.
_URL_HELPER = re.compile(
    r"\b(?:const|let)\s+(\w+)\s*(?::[^=\n]+)?=\s*(?:async\s*)?\([^)]*\)\s*(?::\s*string\s*)?=>\s*"
    r"`\$\{getApiBase\(\)\}(/[^`]*)`(?=[ \t]*(?:[;,)}]|//|$))",  # the template is the WHOLE return value
    re.M,
)
_METHOD_OPTION = re.compile(r"""(['"]?)method\1\s*:\s*['"](?P<verb>\w+)['"]""")
_PATH_TAIL = r"/[^`'\"\s]*"
#: The specifier of each ``import ... from '<specifier>'`` in a file.
_IMPORT_SPEC = re.compile(r"""from\s+['"]([^'"]+)['"]""")
_SOURCE_EXT = re.compile(r"\.(?:ts|tsx|js|vue)$")
_MEMBER = r"(?:\w+\.)?"  # ``deps.`` in front of a receiver or helper handed in as a member of a parameter object
HelperCalls = dict[tuple[str, str], set[str]]


def _own_arguments(text: str, start: int) -> str:
    """The text of the call whose argument list opens at the first ``(`` from *start*, up to its closing ``)``.

    Parentheses are balanced and quoted text is skipped, so the next call's options are never read as this one's.
    """
    open_at = text.index("(", start)
    depth, quote = 0, ""
    for index in range(open_at, len(text)):
        char = text[index]
        if quote:
            quote = "" if char == quote and text[index - 1] != "\\" else quote
        elif char in "'\"`":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[open_at : index + 1]
    return text[open_at:]


def _method_key_at(arguments: str, index: int, stack: list[str]) -> str:
    """The verb of a ``method:`` key (bare or quoted) at *index* of the call's own options object, else ``""``."""
    if stack != ["(", "{"] or arguments[:index].rstrip()[-1:] not in ("{", ","):
        return ""
    option = _METHOD_OPTION.match(arguments, index)
    return option.group("verb") if option else ""


def _top_level_method(arguments: str) -> str:
    """The ``method:`` of the call's own options object, or ``""``: nested objects and quoted text are skipped."""
    stack: list[str] = []
    quote = ""
    for index, char in enumerate(arguments):
        if quote:
            quote = "" if char == quote and arguments[index - 1] != "\\" else quote
        elif verb := _method_key_at(arguments, index, stack):
            return verb
        elif char in "'\"`":
            quote = char
        elif char in "({[":
            stack.append(char)
        elif char in ")}]":
            stack.pop()
    return ""


def _verb(verb: str, arguments: str) -> str:
    """The HTTP method of a client call: its own verb, or the ``method:`` option of ``rawRequest``/``request``."""
    if verb in ("rawRequest", "request"):
        return (_top_level_method(arguments) or "GET").upper()
    return verb.upper() if verb in ("get", "post", "put", "patch", "delete") else ""


def _calls_of(
    helper: re.Match[str],
    calls: str,
    receivers: dict[str, str],
    handed_in: bool = False,
) -> set[tuple[str, str]]:
    """The calls in *calls* through *helper*; *handed_in* reads the client and the helper as members of a parameter."""
    member = _MEMBER if handed_in else ""
    name, path = member + helper.group(1), "/api" + helper.group(2)
    names = member + "(?:" + "|".join(re.escape(n) for n in sorted(receivers, key=len, reverse=True)) + ")"
    arg = rf"(?:`\$\{{{name}\(\)\}}({_PATH_TAIL})?`|{name}\(\))\s*[,)]"
    site = re.compile(rf"(?<![\w.$]){names}\s*\.\s*({_VERBS})\s*(?:<[^()]*>)?\s*\(\s*{arg}")
    found = set()
    for m in site.finditer(calls):
        if verb := _verb(m.group(1), _own_arguments(calls, m.end(1))):
            found.add((verb, path + (m.group(2) or "")))
    return found


def helper_calls_in(rel: str, text: str) -> set[tuple[str, str]]:
    """``(METHOD, raw path)`` of each client call in one file that goes through a same-file URL helper."""
    receivers, _script, calls = prepared_text(rel, text)
    found: set[tuple[str, str]] = set()
    for helper in _URL_HELPER.finditer(calls):
        found |= _calls_of(helper, calls, receivers)
    return found


def _imported_modules(rel: str, text: str) -> set[str]:
    """The extension-less repo paths *rel* imports: a relative specifier against *rel*'s directory, the ``@/``
    alias against the ``src`` root *rel* sits under. A bare package specifier names no repo file."""
    root = rel.split("/src/", 1)[0] + "/src" if "/src/" in rel else ""
    out = set()
    for spec in _IMPORT_SPEC.findall(text):
        if spec.startswith("."):
            target = posixpath.normpath(posixpath.join(posixpath.dirname(rel), spec))
        elif spec.startswith("@/") and root:
            target = posixpath.join(root, spec[2:])
        else:
            continue
        out.add(_SOURCE_EXT.sub("", target))
    return out


def _is_module(other: str, modules: set[str]) -> bool:
    """True when *other* is one of the *modules* (or the ``index`` of a directory among them)."""
    bare = _SOURCE_EXT.sub("", other)
    return bare in modules or (bare.endswith("/index") and bare[: -len("/index")] in modules)


def _handed_in_calls(rel: str, text: str, texts: dict[str, str]) -> HelperCalls:
    """The calls through *rel*'s URL helpers made in the files it imports, which it hands the helper and client."""
    receivers, _script, own_calls = prepared_text(rel, text)
    helpers = list(_URL_HELPER.finditer(own_calls))
    modules = _imported_modules(rel, text)
    out: HelperCalls = {}
    for other, other_text in texts.items():
        if other == rel or not helpers or not _is_module(other, modules):
            continue
        calls = prepared_text(other, other_text)[2]
        for helper in helpers:
            for found in _calls_of(helper, calls, receivers, handed_in=True):
                out.setdefault(found, set()).add(other)
    return out


def helper_calls(tree: Tree, frontends: tuple[str, ...], norm_path, exclude: tuple[str, ...]) -> HelperCalls:
    """``{(METHOD, normalised path): {files}}`` for the helper-built calls, tests/mocks out."""
    texts = {
        rel: tree.text(rel)
        for rel in tree.select(".ts", ".vue", ".js", ".tsx", under=frontends)
        if not any(x in rel for x in exclude)
    }
    raw: HelperCalls = {}
    for rel, text in texts.items():
        if "getApiBase" not in text:
            continue
        for found in helper_calls_in(rel, text):
            raw.setdefault(found, set()).add(rel)
        for found, files in _handed_in_calls(rel, text, texts).items():
            raw.setdefault(found, set()).update(files)
    out: HelperCalls = {}
    for (verb, call), files in raw.items():
        path = norm_path(call)
        if path.count("{") == path.count("}"):
            out.setdefault((verb, path), set()).update(files)
    return out


def strict_match(call: str, route: str) -> bool:
    """Same depth; each segment equal or the route's is a parameter: a call placeholder never meets a literal."""
    a, b = call.strip("/").split("/"), route.strip("/").split("/")
    return len(a) == len(b) and all(x == y or y == "{p}" for x, y in zip(a, b))


def reached_by_helper(rel: str, method: str, cands: tuple[str, ...], calls: HelperCalls, toggle_api) -> bool:
    """Whether a helper-built call from another file has *method* and strictly matches one of the route's paths."""
    for cand in cands:
        for variant in {cand, toggle_api(cand)}:
            for (verb, path), files in calls.items():
                if verb == method.upper() and strict_match(path, variant) and files - {rel}:
                    return True
    return False
