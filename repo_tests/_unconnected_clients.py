# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Frontend calls made through an HTTP client with a base URL (#20512).

``scripts/audit_api_wiring.frontend_calls`` sees a literal ``/api/...`` or ``${getApiBase()}/...``.
Both frontends also call relative paths through a client that supplies the base, so
``slmApiClient.get('/api-keys')`` never names ``/api``. This resolves those, one client form at a time.

THE CLIENT FORMS (receiver recognised -> the base its relative path gets)
-------------------------------------------------------------------------
SLM frontend (``autobot-slm-frontend/src/utils/ApiClient.ts``, ``SlmApiClient.resolveBaseUrl``):

* ``slmApiClient`` (named import/default) and ``const x = new SlmApiClient()`` -> ``getSlmApiBase()``
  = ``<apiBaseUrl>/api`` (``/api`` standalone, ``/slm/api`` co-located). Both reach the same route
  ``/api/...`` on the SLM backend, so the call is ``/api`` + path.
* ``const x = makeAxiosCompatClient(...)`` (``utils/slmApiCompat.ts``) -> delegates to ``slmApiClient``:
  the same ``/api`` base.
* ``const x = createAutobotBackendClient()`` (``composables/useAutobotApi.ts``) -> an ``SlmApiClient``
  whose base is ``setBaseUrl(getBackendUrl())`` = ``/autobot-api``, an nginx proxy to the MAIN backend.
  Whether the proxy adds ``/api`` is not in the repo's TypeScript, so the call is counted as ``/api`` +
  path (loose: it errs toward "connected").
* ``${getSlmApiBase()}/x`` in a template -> ``/api`` + ``/x`` (same base, written out).

Two file-local forms resolve to those clients (#20910):

* a path constant, ``const SETUP_RESET = '/setup/reset'`` (or a template, ``const url = `/x${qs}` ``):
  ``client.post(SETUP_RESET)``, ``${LEDGER}/claims`` and ``wrapper(url)`` read as the value. The latest
  declaration above the use applies, whichever function declared it.
* a request wrapper, ``function read(path: string) { ... client.rawRequest(`${LEDGER}${path}`) }`` or
  ``async function apiRequest(method, path) { ... client.get(path) }``: a call ``read('/claims')`` or
  ``apiRequest('GET', '/config/defaults')`` is the client's base + the wrapper's prefix + the path.

Main frontend (``autobot-frontend/src/utils/ApiClient.ts``): the base is the host (``baseUrl`` is
``''`` in proxy mode) and the ``/api`` is written at the call site, which ``frontend_calls`` already
reads. A relative ``/x`` through ``apiClient`` / ``useApiClient()`` / ``new ApiClient()`` therefore
requests ``/x`` at the host root, so it is counted as ``/x`` with no ``/api``.

HOW A CALL SITE MAPS TO A ROUTE
-------------------------------
``<receiver>.<verb>(`` + a string whose first character is ``/`` (not ``/api/``, which
``frontend_calls`` owns) -> ``base + path`` -> ``norm_path`` -> compared to every candidate full path
of a route by ``_unconnected_routes._reached``, exactly like a literal ``/api/...`` caller.

WHAT THIS CANNOT SEE
--------------------
* A client held in a field, parameter or returned from a function other than the three factories
  above (``this.client.get``, ``getClient().get``): the receiver is not a recognised name.
* A path held in a variable (``get(url)``) or concatenated from a base variable (``get(base + '/x')``).
* A receiver name reused for two different clients in one file: the file's declarations are merged.
* A call that is dead (the function making it is never invoked), and any ``fetch``/``axios`` call.
* A wrapper that is an arrow function or a method, or whose body passes its path to the client in any form
  other than the bare parameter or ``${PREFIX}${param}``; a wrapper call whose leading arguments before the
  path are not plain string literals.
* A path constant built by concatenation, or one whose value does not start with ``/``.
"""

from __future__ import annotations

import re

from repo_tests._unconnected_common import Tree

_VERBS = r"(?:get|post|put|patch|delete|getContract|rawRequest|upload\w*|request)"
_PATH = r"""(?:<[^()]*>)?\s*\(\s*[`'"](/[^`'"\s]*)"""

#: Receivers that are a client wherever they appear, and the base their relative paths get.
_NAMED = {"slmApiClient": "/api"}
#: ``const x = <factory>`` declarations that make ``x`` a client with the given base.
_DECLARED = (
    (re.compile(r"\b(?:const|let)\s+(\w+)\s*=\s*(?:new\s+SlmApiClient|makeAxiosCompatClient)\s*\("), "/api"),
    (re.compile(r"\b(?:const|let)\s+(\w+)\s*=\s*createAutobotBackendClient\s*\("), "/api"),
    (re.compile(r"\b(?:const|let)\s+(\w+)\s*=\s*(?:new\s+ApiClient|useApiClient|getApiClient)\s*\("), ""),
)
#: Main-frontend names that are the canonical client wherever they appear.
_MAIN_NAMED = {"apiClient": ""}
_SLM_BASE_CALL = re.compile(r"\$\{getSlmApiBase\(\)\}(/[^`'\"\s]*)")
_COMMENT_PREFIXES = ("* ", "//", "/*")
#: ``const NAME = '/path'`` or a template; a ``${...}`` counts only as a whole segment (``/x/${id}/y``), so a
#: query glued on (``/x${qs ? ...}``) ends the value.
_PATH_CONST = re.compile(
    r"""\b(?:const|let)\s+(\w+)\s*(?::\s*string\s*)?=\s*[`'"]""" r"""(/(?:[\w.\-/]|\$\{[^}`'"\n]*\}(?=[/`'"]))*)"""
)
#: ``[async] function name<T>(params)``: a candidate request wrapper.
_FUNCTION = re.compile(r"(?:async\s+)?function\s+(\w+)\s*(?:<[^()]*>)?\s*\(([^)]*)\)")
#: How far into a wrapper's body its client call is looked for.
_WRAPPER_BODY = 1500
_SLM_ROOT = "autobot-slm-frontend/src"
_MAIN_ROOT = "autobot-frontend/src"


def _receivers(rel: str, text: str) -> dict[str, str]:
    """``{receiver name: base}`` for the clients this file can name."""
    found = dict(_NAMED if rel.startswith(_SLM_ROOT) else _MAIN_NAMED)
    for decl, base in _DECLARED:
        for name in decl.findall(text):
            found[name] = base
    return found


def _site_pattern(receivers: dict[str, str]) -> re.Pattern[str]:
    names = "|".join(re.escape(n) for n in sorted(receivers, key=len, reverse=True))
    return re.compile(rf"(?<![\w.$])({names})\s*\.\s*{_VERBS}\s*{_PATH}")


def _inline_constants(lines: list[str]) -> str:
    """The text with each file-local path constant replaced by its value where a call can use it."""
    consts: dict[str, str] = {}
    out: list[str] = []
    for line in lines:
        for name, value in consts.items():
            line = line.replace("${" + name + "}", value)
            line = re.sub(rf"(\(\s*){name}(?=\s*[,)])", rf"\g<1>'{value}'", line)
        consts.update(_PATH_CONST.findall(line))
        out.append(line)
    return "\n".join(out)


def _wrappers(text: str, receivers: dict[str, str]) -> dict[str, tuple[int, str]]:
    """``{wrapper: (index of its path argument, base + prefix)}`` for functions that hand a path to a client."""
    names = "|".join(re.escape(n) for n in sorted(receivers, key=len, reverse=True))
    found: dict[str, tuple[int, str]] = {}
    for fn in _FUNCTION.finditer(text):
        params = [p.split(":")[0].split("=")[0].strip(" ?\t\n") for p in fn.group(2).split(",")]
        body = text[fn.end() : fn.end() + _WRAPPER_BODY]
        for index, param in enumerate(params):
            arg = rf"(?:`(/[^`'\"\s$]*)\$\{{{param}\}}`|{param}\b)" if param.isidentifier() else None
            hit = arg and re.search(rf"(?<![\w.$])({names})\s*\.\s*{_VERBS}\s*(?:<[^()]*>)?\s*\(\s*{arg}", body)
            if hit:
                found[fn.group(1)] = (index, receivers[hit.group(1)] + (hit.group(2) or ""))
                break
    return found


def _wrapper_calls(text: str, wrappers: dict[str, tuple[int, str]]) -> set[str]:
    """``base + prefix + path`` for each call of a wrapper with a literal path at its path argument."""
    out: set[str] = set()
    for name, (index, base) in wrappers.items():
        lead = r"\s*[`'\"][^`'\"]*[`'\"]\s*," * index
        call = re.compile(rf"(?<![\w.$]){name}\s*(?:<[^()]*>)?\s*\({lead}\s*[`'\"](/[^`'\"\s]*)")
        out.update(base + m.group(1) for m in call.finditer(text))
    return out


def _file_calls(rel: str, text: str) -> set[str]:
    """Raw ``base + path`` strings the client calls in one file make.

    Comment lines are blanked and the call is matched across the whole text, so a call whose path
    sits on the line after ``client.post<T>(`` is seen (``_PATH`` already allows the newline).
    """
    receivers = _receivers(rel, text)
    pattern, out = _site_pattern(receivers), set[str]()
    lines = ["" if (ln.lstrip()[:2] in _COMMENT_PREFIXES or ln.strip() == "*") else ln for ln in text.splitlines()]
    code = _inline_constants(lines)
    out.update(receivers[m.group(1)] + m.group(2) for m in pattern.finditer(code) if m.group(2) != "/api")
    out.update(_wrapper_calls(code, _wrappers(code, receivers)))
    if rel.startswith(_SLM_ROOT):
        for line in lines:
            out.update("/api" + suffix for suffix in _SLM_BASE_CALL.findall(line))
    return {c for c in out if not c.startswith("/api/api/")}


def client_calls(tree: Tree, frontends: tuple[str, ...], norm_path, exclude: tuple[str, ...]) -> dict[str, set[str]]:
    """``{normalised path: {files}}`` for relative calls through a recognised client, tests/mocks out."""
    calls: dict[str, set[str]] = {}
    for rel in tree.select(".ts", ".vue", ".js", ".tsx", under=frontends):
        if any(x in rel for x in exclude):
            continue
        text = tree.text(rel)
        if "/" not in text:
            continue
        for raw in _file_calls(rel, text):
            path = norm_path(raw)
            if path.count("{") == path.count("}"):
                calls.setdefault(path, set()).add(rel)
    return calls
