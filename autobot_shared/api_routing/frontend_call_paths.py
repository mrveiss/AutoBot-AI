# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request-URL extraction from frontend source, shared by the api-wiring audit (#20910).

``scripts/audit_api_wiring.py`` calls ``call_paths`` for every frontend file to learn which backend paths the
frontend calls. Each way the frontend builds a request URL that has real call sites is handled here: literal
``/api/`` strings, ``getApiBase()``, ``getBackendUrl()``, other host placeholders before ``/api/`` and file-local
base constants.
"""

from __future__ import annotations

import re

FE_API_RE = re.compile(r"[\'\"`](/api/[A-Za-z0-9_/${}():.\-]+)")
# #12326: the dominant idiom composes the path from a helper —
# ``apiClient.get(`${getApiBase()}/knowledge_base/health/status`)``. getApiBase()
# resolves to '/api' (see ssot-config.ts:getApiBase), so the real call target is
# ``/api`` + the captured suffix. Without this the audit only saw literal
# ``'/api/...'`` strings (~42% of calls) and reported a clean bill while dozens of
# ``${getApiBase()}/...`` calls hit non-existent routes.
GETAPIBASE_CALL_RE = re.compile(r"\$\{getApiBase\(\)\}(/[A-Za-z0-9_/${}():.\-]+)")
# #10037: ``${getBackendUrl()}/<path>`` calls. getBackendUrl() is host-level
# (no /api), so any <path> that omits /api hits a path the backend doesn't
# serve. We only flag the high-confidence case where /api<path> IS a real
# route (a forgotten /api, the #10036 class) — never legit non-/api mounts.
BACKEND_URL_CALL_RE = re.compile(r"\$\{getBackendUrl\(\)\}(/[A-Za-z0-9_/${}():.\-]+)")
# #20910: ONE rule for "a URL base directly before `/api/`", for frontend and non-frontend callers alike. The base is a
# placeholder (`${API_BASE}`, `${NetworkConstants.getBackendUrl()}`, shell `$BASE` or `"$BASE"`, python `{base}`,
# jinja `{{ backend_url }}`) or a literal host (`http://localhost:8001`, `:8001`). A directory name before `/api/`
# (`autobot-backend/api/x.py`) is a file path, not a base, and does not match. `${getApiBase()}` is not a host: it is
# `/api` itself, so `${getApiBase()}/api/x` is `/api/api/x` and is left to GETAPIBASE_CALL_RE.
URL_BASE_API_RE = re.compile(
    r"(?:\$\{(?!getApiBase\(\))[^}\n]*\}|\$[A-Za-z_]\w*\"?|\{{1,2}(?!getApiBase\(\))[^{}\n]+\}{1,2}"
    r"|:\d{2,5}|(?:https?|wss?)://[\w.\-]+)"
    r"(/api/[A-Za-z0-9_/${}():.\-]+)"
)
# #20910: a file-local base constant that names an /api path, which later calls extend:
# ``const API_BASE = `${getApiBase()}/knowledge-graph` `` then ``${API_BASE}/entities``. The value may itself hold
# placeholders (``const base = `/api/llc/roles/${companyId.value}/${roleId}` ``): they become path parameters.
BASE_CONST_RE = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*(?::\s*string\s*)?=\s*[`'\"]"
    r"((?:/api|\$\{getApiBase\(\)\}|\$\{getBackendUrl\(\)\}/api)(?:[A-Za-z0-9_/\-]|\$\{[^}`'\"\n]*\})*)[`'\"]\s*;?\s*$",
    re.MULTILINE,
)


def _resolve_base(value: str) -> str:
    """A base constant's value as a path: ``${getApiBase()}`` is ``/api``, ``${getBackendUrl()}`` is the host."""
    return value.replace("${getApiBase()}", "/api").replace("${getBackendUrl()}", "")


#: How many passes resolve a base that extends another base before giving up (a longer chain is not a real file).
_MAX_BASE_DEPTH = 5


def _base_constants(lines: list[str]) -> dict[str, list[str]]:
    """``{NAME: [/api/... paths]}`` for the file-local base constants.

    A name may be declared again in another function with another value, so every value is kept. A constant may
    extend an earlier one.
    """
    bases: dict[str, list[str]] = {}
    text = "\n".join(lines)
    for _ in range(_MAX_BASE_DEPTH):
        resolved: dict[str, list[str]] = {}
        for name, value in BASE_CONST_RE.findall(text):
            for other, paths in resolved.items():
                value = value.replace("${" + other + "}", paths[-1])
            resolved.setdefault(name, []).append(_resolve_base(value))
        if resolved == bases:
            break
        bases = resolved
    return bases


def call_paths(txt: str) -> list[str]:
    """Raw path strings the frontend calls named in one file's text (comment lines skipped)."""
    lines = [
        ln for ln in txt.splitlines() if ln.lstrip()[:2] not in ("* ", "//", "/*") and ln.strip() != "*"
    ]  # comment lines hold doc EXAMPLES (`* apiClient.get('/api/users')`), not real calls
    bases = _base_constants(lines)
    found: list[str] = []
    for line in lines:
        # Literal '/api/...' strings and getApiBase()-composed paths (#12326): getApiBase() is '/api'.
        found += FE_API_RE.findall(line)
        found += ["/api" + s for s in GETAPIBASE_CALL_RE.findall(line)]
        # `${getBackendUrl()}/<path>` (host-level, so the path is the call target) and other host placeholders.
        found += BACKEND_URL_CALL_RE.findall(line)
        found += URL_BASE_API_RE.findall(line)
        for name, paths in bases.items():
            tails = re.findall(r"\$\{" + name + r"\}(/[A-Za-z0-9_/${}():.\-]+)", line)
            tails += re.findall(r"\b" + name + r"\s*\+\s*[`'\"](/[A-Za-z0-9_/${}():.\-]+)", line)
            found += [base + t for base in paths for t in tails]
    return found
