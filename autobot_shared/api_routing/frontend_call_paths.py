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
# (`autobot-backend/api/x.py`) is a file path, not a base, and does not match.
URL_BASE_API_RE = re.compile(
    r"(?:\$\{[^}\n]*\}|\$[A-Za-z_]\w*\"?|\{{1,2}[^{}\n]+\}{1,2}|:\d{2,5}|(?:https?|wss?)://[\w.\-]+)"
    r"(/api/[A-Za-z0-9_/${}():.\-]+)"
)
# #20910: a file-local base constant that names an /api path, which later calls extend:
# ``const API_BASE = `${getApiBase()}/knowledge-graph` `` then ``${API_BASE}/entities``.
BASE_CONST_RE = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*(?::\s*string\s*)?=\s*[`'\"]"
    r"((?:/api|\$\{getApiBase\(\)\}|\$\{getBackendUrl\(\)\}/api)[A-Za-z0-9_/\-]*)[`'\"]\s*;?\s*$",
    re.MULTILINE,
)


def _resolve_base(value: str) -> str:
    """A base constant's value as a path: ``${getApiBase()}`` is ``/api``, ``${getBackendUrl()}`` is the host."""
    return value.replace("${getApiBase()}", "/api").replace("${getBackendUrl()}", "")


def _base_constants(lines: list[str]) -> dict[str, str]:
    """``{NAME: /api/... path}`` for the file-local base constants (a constant may extend an earlier one)."""
    bases: dict[str, str] = {}
    for _ in range(2):
        for name, value in BASE_CONST_RE.findall("\n".join(lines)):
            for other, path in bases.items():
                value = value.replace("${" + other + "}", path)
            bases[name] = _resolve_base(value)
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
        for name, base in bases.items():
            found += [base + t for t in re.findall(r"\$\{" + name + r"\}(/[A-Za-z0-9_/${}():.\-]+)", line)]
            found += [base + t for t in re.findall(r"\b" + name + r"\s*\+\s*[`'\"](/[A-Za-z0-9_/${}():.\-]+)", line)]
    return found
