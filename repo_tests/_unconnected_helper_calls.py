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

Only a call through a recognised client receiver counts (``console.log(`${h()}/x`)`` and ``fetch`` do not), and a
helper declared in another file is not followed.
"""

from __future__ import annotations

import re

from repo_tests._unconnected_clients import _VERBS, prepared_text
from repo_tests._unconnected_common import Tree

#: ``const name = (args)[: string] =>`` then a ``${getApiBase()}/...`` template: a URL helper.
_URL_HELPER = re.compile(
    r"\b(?:const|let)\s+(\w+)\s*(?::[^=\n]+)?=\s*(?:async\s*)?\([^)]*\)\s*(?::\s*string\s*)?=>\s*"
    r"`\$\{getApiBase\(\)\}(/[^`]*)`"
)
_METHOD_OPTION = re.compile(r"method\s*:\s*['\"](\w+)['\"]")
_OPTIONS_WINDOW = 200
_PATH_TAIL = r"/[^`'\"\s]*"
HelperCalls = dict[tuple[str, str], set[str]]


def _verb(verb: str, after: str) -> str:
    """The HTTP method of a client call: its own verb, or the ``method:`` option of ``rawRequest``/``request``."""
    if verb in ("rawRequest", "request"):
        option = _METHOD_OPTION.search(after[:_OPTIONS_WINDOW])
        return option.group(1).upper() if option else "GET"
    return verb.upper() if verb in ("get", "post", "put", "patch", "delete") else ""


def _calls_of(helper: re.Match[str], calls: str, receivers: dict[str, str]) -> set[tuple[str, str]]:
    name, path = helper.group(1), "/api" + helper.group(2)
    names = "|".join(re.escape(n) for n in sorted(receivers, key=len, reverse=True))
    arg = rf"(?:`\$\{{{name}\(\)\}}({_PATH_TAIL})?`?|{name}\(\)\s*[,)])"
    site = re.compile(rf"(?<![\w.$])(?:{names})\s*\.\s*({_VERBS})\s*(?:<[^()]*>)?\s*\(\s*{arg}")
    found = set()
    for m in site.finditer(calls):
        if verb := _verb(m.group(1), calls[m.end() :]):
            found.add((verb, path + (m.group(2) or "")))
    return found


def helper_calls_in(rel: str, text: str) -> set[tuple[str, str]]:
    """``(METHOD, raw path)`` of each client call in one file that goes through a same-file URL helper."""
    receivers, _script, calls = prepared_text(rel, text)
    found: set[tuple[str, str]] = set()
    for helper in _URL_HELPER.finditer(calls):
        found |= _calls_of(helper, calls, receivers)
    return found


def helper_calls(tree: Tree, frontends: tuple[str, ...], norm_path, exclude: tuple[str, ...]) -> HelperCalls:
    """``{(METHOD, normalised path): {files}}`` for the helper-built calls, tests/mocks out."""
    out: HelperCalls = {}
    for rel in tree.select(".ts", ".vue", ".js", ".tsx", under=frontends):
        if any(x in rel for x in exclude):
            continue
        text = tree.text(rel)
        if "getApiBase" not in text:
            continue
        for verb, raw in helper_calls_in(rel, text):
            path = norm_path(raw)
            if path.count("{") == path.count("}"):
                out.setdefault((verb, path), set()).add(rel)
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
