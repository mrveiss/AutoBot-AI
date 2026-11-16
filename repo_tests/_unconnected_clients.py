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
* A wrapper's body is read from its ``{`` to the matching ``}`` (#20910), comments removed by the shared stripper
  and string and template text skipped. A regex literal holding a brace or quote, or an object-literal return type
  (``): { a: number } {``, whose ``{`` is taken as the body), can still end the body early (the wrapper is missed)
  or late (a later client call is read as its own).
* A path constant whose whole initialiser is not one literal path (``'/a' + '/b'``, ``base + '/x'``, a value not
  starting with ``/``), and a constant set inside a statement that does not start the line (``if (x) { const u =``).
* A wrapper parameter rebound by an expression arrow in its body (``items.map((path) => client.get(path))``): the
  parameter is then not read as handed to the client at all, so a real wrapper of that shape is missed.
* A wrapper call inside a ``.vue`` template expression that holds a ``//`` or ``/* */`` text: the template is read
  with only its ``<!-- -->`` comments removed.
"""

from __future__ import annotations

import re

from repo_tests._ui_literal_scan import SCRIPT_BODY
from repo_tests._unconnected_common import Tree
from repo_tests._unconnected_frontend import frontend_code_text

from tools.lint._comment_syntax import strip_html_comments

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
#: A whole initialiser that is ONE literal path: ``'/x'``, ``\`/x/${id}\``` or ``\`/x${query}\```, then at most ``;``
#: and a trailing comment. A ``${...}`` counts as a segment only when whole (``/x/${id}/y``); one glued on at the end
#: is a query (``norm_path`` drops it). ``'/a' + '/b'`` and ``base + '/x'`` are not one literal (#20910).
_WHOLE_PATH = re.compile(r"""([`'"])(/(?:[\w.\-/]|\$\{[^}`'"\n]*\}(?=[/`'"]))*)(?:\$\{.*\})?\1\s*;?\s*(?://.*)?$""")
#: One assignment statement: ``[export] [const|let|var] name[: string] [op]= value``.
_ASSIGN = re.compile(
    r"^[\s{]*(?:export\s+)?(?:(const|let|var)\s+)?(\w+)\s*(?::\s*string\s*)?([-+*/%|&?]*)=(?![=>])(.*)$"
)
#: ``[async] function name<T>(params)``: a candidate request wrapper.
_FUNCTION = re.compile(r"(?:async\s+)?function\s+(\w+)\s*(?:<[^()]*>)?\s*\(([^)]*)\)")
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


def _track(statement: str, consts: dict[str, str]) -> None:
    """Record, update or forget a path constant from one assignment statement.

    A declaration or a plain reassignment whose whole value is one literal path sets the name; any other value, or a
    compound assignment (``url += '/x'``), forgets it, so a later use is not read as the stale literal (#20910).
    """
    assigned = _ASSIGN.match(statement)
    if assigned is None:
        return
    keyword, name, op, value = assigned.groups()
    whole = None if op else _WHOLE_PATH.match(value.strip())
    if whole is not None and (keyword or name in consts):
        consts[name] = whole.group(2)
    else:
        consts.pop(name, None)


def _inline_constants(lines: list[str]) -> str:
    """The text with each file-local path constant replaced by its value where a call can use it.

    Statements are read in order (a line split at ``;``), so a value set or forgotten earlier on a line applies to
    the rest of it.
    """
    consts: dict[str, str] = {}
    out: list[str] = []
    for line in lines:
        statements = line.split(";")
        for index, statement in enumerate(statements):
            for name, value in consts.items():
                statement = statement.replace("${" + name + "}", value)
                statement = re.sub(rf"(\(\s*){name}(?=\s*[,)])", rf"\g<1>'{value}'", statement)
            statements[index] = statement
            _track(statement, consts)
        out.append(";".join(statements))
    return "\n".join(out)


def _body_open(text: str, start: int) -> int:
    """Index of the ``{`` opening the body after a signature ending at *start*; a return type's ``<...>`` is skipped."""
    angle, index = 0, start
    while index < len(text):
        char = text[index]
        if char == "<":
            angle += 1
        elif char == ">" and text[index - 1] != "=":
            angle -= 1
        elif char == "{" and angle <= 0:
            return index
        elif char == ";" and angle <= 0:
            return -1  # a declaration with no body (an overload signature)
        index += 1
    return -1


def _literal_step(text: str, index: int, stack: list[str]) -> int:
    """One step inside a string or template literal: the next index. Ends the literal, or opens a ``${`` as code."""
    char, top = text[index], stack[-1]
    if char == "\\":
        return index + 2
    if char == top:
        stack.pop()
    elif top == "`" and text.startswith("${", index):
        stack.append("{")
        return index + 2
    return index + 1


def _block_end(text: str, opener: int) -> int:
    """Index just past the ``}`` closing the ``{`` at *opener*, string and template text skipped (comments are gone).

    A template's ``${...}`` is code again, so a brace or a nested template inside it is read as code.
    """
    stack: list[str] = []
    index = opener
    while index < len(text):
        if stack and stack[-1] in ("'", '"', "`"):
            index = _literal_step(text, index, stack)
            continue
        char = text[index]
        if char in ("'", '"', "`", "{"):
            stack.append(char)
        elif char == "}" and stack:
            stack.pop()
            if not stack:
                return index + 1
        index += 1
    return len(text)


def _function_body(text: str, signature_end: int) -> str:
    """The body of the function whose signature ends at *signature_end*, from its ``{`` to the matching ``}``."""
    opener = _body_open(text, signature_end)
    return "" if opener < 0 else text[opener : _block_end(text, opener)]


#: The start of a function nested in a body: ``function [name](params)`` or a block arrow ``=> {``.
_INNER = re.compile(r"\bfunction\b[^(]*\([^)]*\)|=>\s*(?=\{)")


def _own_body(body: str) -> str:
    """*body* without the bodies of the functions nested in it: their client calls are theirs (#20910)."""
    kept, index = [], 1  # past the body's own `{`
    for inner in _INNER.finditer(body, 1):
        if inner.start() < index:
            continue  # inside a nested body already cut
        opener = _body_open(body, inner.end()) if inner.group().startswith("function") else body.find("{", inner.end())
        if opener < 0:
            continue
        kept.append(body[index : inner.start()])
        index = _block_end(body, opener)
    return "".join(kept) + body[index:]


def _rebinds(body: str, param: str) -> bool:
    """Whether an expression arrow in *body* binds its own *param* (``(path) => client.get(path)``)."""
    return re.search(rf"(?:\b{param}|\([^()]*\b{param}\b[^()]*\))\s*(?::[^=()]*)?=>", body) is not None


def _wrapper_hit(body: str, params: list[str], names: str) -> tuple[int, re.Match[str]] | None:
    """``(index, match)`` of the first parameter *body* hands, whole and untransformed, to a client call."""
    for index, param in enumerate(params):
        if not param.isidentifier() or _rebinds(body, param):
            continue
        arg = rf"(?:`(/[^`'\"\s$]*)\$\{{{param}\}}`|{param})\s*[,)]"
        hit = re.search(rf"(?<![\w.$])({names})\s*\.\s*{_VERBS}\s*(?:<[^()]*>)?\s*\(\s*{arg}", body)
        if hit:
            return index, hit
    return None


def _wrappers(script: str, receivers: dict[str, str]) -> dict[str, tuple[int, str]]:
    """``{wrapper: (index of its path argument, base + prefix)}`` for functions that hand a path to a client.

    *script* is the file's code without comments (``_unconnected_frontend.frontend_code_text``: each file in its own
    syntax, a ``.vue`` file's ``<script>`` blocks only), so a brace or quote in a comment or in template prose cannot
    end a body. Only the function's own body counts, and only an argument that is the parameter itself.
    """
    names = "|".join(re.escape(n) for n in sorted(receivers, key=len, reverse=True))
    found: dict[str, tuple[int, str]] = {}
    for fn in _FUNCTION.finditer(script):
        params = [p.split(":")[0].split("=")[0].strip(" ?\t\n") for p in fn.group(2).split(",")]
        hit = _wrapper_hit(_own_body(_function_body(script, fn.end())), params, names)
        if hit is not None:
            index, match = hit
            found[fn.group(1)] = (index, receivers[match.group(1)] + (match.group(2) or ""))
    return found


def _wrapper_calls(text: str, wrappers: dict[str, tuple[int, str]]) -> set[str]:
    """``base + prefix + path`` for each call of a wrapper with a literal path at its path argument."""
    out: set[str] = set()
    for name, (index, base) in wrappers.items():
        lead = r"\s*[`'\"][^`'\"]*[`'\"]\s*," * index
        call = re.compile(rf"(?<![\w.$]){name}\s*(?:<[^()]*>)?\s*\({lead}\s*[`'\"](/[^`'\"\s]*)")
        out.update(base + m.group(1) for m in call.finditer(text))
    return out


def _call_text(rel: str, code: str, script: str) -> str:
    """The text wrapper calls are read from: *script* (comments stripped), plus a ``.vue`` template's markup without
    its ``<!-- -->`` comments, where a handler may call a wrapper (#20910)."""
    if not rel.endswith(".vue"):
        return script
    return script + "\n" + strip_html_comments(SCRIPT_BODY.sub("", code))


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
    script = frontend_code_text(rel, code)
    out.update(_wrapper_calls(_call_text(rel, code, script), _wrappers(script, receivers)))
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
