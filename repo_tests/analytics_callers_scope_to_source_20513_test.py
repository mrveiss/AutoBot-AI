# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every frontend call to a source-scoped analytics route sends its source (#20513).

The analytics routes answer 422 without ``source_id``, and ``withSourceId`` / ``sourceIdQuery`` add
nothing when no source is selected -- so a caller that forgets them is a page that breaks the moment
it is opened. This reads the frontend source for every ``/analytics/codebase/<path>`` literal and
requires scope evidence beside each one that is not on a named exempt list.

Evidence, in the lines around the literal (3 before, 8 after): ``withSourceId(``, ``sourceIdQuery``,
an explicit ``source_id``, or ``scopeToSource: true`` in a file that injects ``withSourceId``. A task
factory (``useBackgroundTask`` / ``useTaskLoader``) names the base URL once and sends the source with
``start()`` / ``load()``, so it needs ``sourceIdQuery`` or ``source_id`` somewhere in its file.

Limits, stated: this reads text, not the call graph. A neighbouring call's evidence can fall inside
another literal's window, so it can miss a bare call placed right beside a scoped one; the planted
controls below show the cases it does catch. The backend route guard (``routes_require_source_20513_test``)
is the check that no route can be called without a source at all.
"""

from __future__ import annotations

import re

import pytest
from repo_tests._analytics_routes_20513 import CROSS_SOURCE_PATHS, DEFERRED_TO_PR2, OPS_SUFFIXES
from repo_tests._paths import repo_root

FRONTEND_SRC = "autobot-frontend/src"
MIN_SITES_EXAMINED = 30

LITERAL = re.compile(r"(?:/api|\$\{getApiBase\(\)\})/analytics/codebase/([A-Za-z0-9_\-/{}$.]+)")
EVIDENCE = re.compile(r"withSourceId\(|sourceIdQuery|source_id")
SCOPE_FLAG = re.compile(r"scopeToSource:\s*true")
TASK_FACTORY = re.compile(r"use(?:BackgroundTask|TaskLoader)\b")
#: ``/index`` and ``/patterns/analyze`` carry the source in a body built a few lines away.
BODY_SCOPED = frozenset({"index", "patterns/analyze"})
#: Source management: ``/sources/{id}...`` and ``/index/queue/{id}`` carry the source as a path parameter.
PATH_PARAM_PREFIXES = ("sources/", "index/queue/")
PR2_REASON = "#20513 PR 2"


def _normalise(raw: str) -> str:
    """``sources/${id}/sync?x=1`` -> ``sources/{x}/sync``."""
    return re.sub(r"\$\{[^}]*\}", "{x}", raw.split("?")[0]).rstrip("/")


def _exempt(path: str) -> str | None:
    """The reason a path needs no scope evidence, or ``None`` if it does."""
    if "/status/" in path or path.endswith(OPS_SUFFIXES) or path.endswith("clear-all"):
        return "task or ops route"
    if f"/{path}" in CROSS_SOURCE_PATHS:
        return "cross-source"
    if f"/{path}" in DEFERRED_TO_PR2:
        return PR2_REASON
    if path.startswith(PATH_PARAM_PREFIXES) or path == "embedding-stats/reset":
        return "source in path / ops"
    return None


def _is_comment(line: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith(("//", "*", "/*"))


def scan_text(text: str) -> tuple[int, list[str]]:
    """``(sites examined, violations)`` for one file's text."""
    lines = text.splitlines()
    file_scopes = "withSourceId" in text
    file_has_source = bool(EVIDENCE.search(text))
    examined, violations = 0, []
    for index, line in enumerate(lines):
        if _is_comment(line):
            continue
        for match in LITERAL.finditer(line):
            path = _normalise(match.group(1))
            if _exempt(path):
                continue
            examined += 1
            span = 12 if path in BODY_SCOPED else None
            window = "\n".join(lines[max(0, index - (span or 3)) : index + (span or 8) + 1])
            ok = bool(EVIDENCE.search(window))
            ok = ok or (bool(SCOPE_FLAG.search(window)) and file_scopes)
            factory = TASK_FACTORY.search("\n".join(lines[max(0, index - 2) : index + 1]))
            ok = ok or (bool(factory) and file_has_source)
            if not ok:
                violations.append(f"line {index + 1}: {path}")
    return examined, violations


def _frontend_files():
    root = repo_root() / FRONTEND_SRC
    for path in sorted(root.rglob("*")):
        if path.suffix not in {".ts", ".vue"}:
            continue
        parts = path.parts
        if "node_modules" in parts or "generated" in parts or "__tests__" in parts:
            continue
        if path.name.endswith((".test.ts", ".spec.ts", ".d.ts")):
            continue
        yield path


def test_every_scoped_analytics_call_sends_its_source():
    total, failures = 0, []
    for path in _frontend_files():
        examined, violations = scan_text(path.read_text(encoding="utf-8"))
        total += examined
        failures += [f"{path.relative_to(repo_root())}: {v}" for v in violations]
    assert total >= MIN_SITES_EXAMINED, f"only {total} call sites examined; the scan stopped seeing them"
    assert not failures, "analytics calls with no source_id (#20513):\n  " + "\n  ".join(failures)


def test_the_exempt_paths_are_the_shared_lists():
    assert _exempt("impact") == "cross-source"
    assert _exempt("patterns/tasks") == "cross-source"
    assert _exempt("index/current") == PR2_REASON
    assert _exempt("patterns/tasks/clear-stuck") == "task or ops route"
    assert _exempt("stats") is None


# --- planted controls: the scan must be able to fail --------------------------------------


@pytest.mark.parametrize(
    "snippet",
    [
        "const d = await apiClient.get('/api/analytics/codebase/stats')",
        "const d = await apiClient.get(`${getApiBase()}/analytics/codebase/duplicates`)",
        "useFetchEndpoint({ path: '/api/analytics/codebase/problems', pickData: (r) => r })",
    ],
)
def test_control_a_bare_call_is_flagged(snippet):
    examined, violations = scan_text(snippet)
    assert examined == 1 and len(violations) == 1


@pytest.mark.parametrize(
    "snippet",
    [
        "const d = await apiClient.get(withSourceId('/api/analytics/codebase/stats'))",
        "await api.get('/api/analytics/codebase/problems', { params: sourceIdQuery.value })",
        "useFetchEndpoint({ path: '/api/analytics/codebase/stats', scopeToSource: true }, { withSourceId })",
        "await post('/api/analytics/codebase/index', { source_id: id })",
    ],
)
def test_control_a_scoped_call_passes(snippet):
    examined, violations = scan_text(snippet)
    assert examined == 1 and violations == []


def test_control_exempt_and_commented_paths_are_not_examined():
    text = "\n".join(
        [
            "api.get('/api/analytics/codebase/sources')",
            "api.get('/api/analytics/codebase/impact?x=1')",
            "api.post(`/api/analytics/codebase/sources/${id}/sync`)",
            "// api.get('/api/analytics/codebase/stats')",
            " * GET /api/analytics/codebase/stats",
        ]
    )
    assert scan_text(text) == (0, [])


def test_control_a_task_factory_needs_the_source_sent_somewhere_in_its_file():
    factory = "const t = useTaskLoader(\n  `${getApiBase()}/analytics/codebase/analytics/import-tree`,\n  pick)"
    assert scan_text(factory)[1], "a factory whose file never sends a source is a bare call"
    assert scan_text(factory + "\nconst go = () => load(undefined, sourceIdQuery.value)")[1] == []


def test_control_a_scope_flag_without_the_injector_is_not_evidence():
    text = "useFetchEndpoint({ path: '/api/analytics/codebase/stats', scopeToSource: true })"
    assert scan_text(text)[1], "scopeToSource alone sends nothing without withSourceId"
