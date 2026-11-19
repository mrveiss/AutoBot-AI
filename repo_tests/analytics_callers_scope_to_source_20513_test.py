# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every frontend call to a source-scoped analytics route sends its source (#20513).

The analytics routes answer 422 without ``source_id``, and ``withSourceId`` / ``sourceIdQuery`` add
nothing when no source is selected -- so a caller that forgets them is a page that breaks the moment
it is opened. This reads the frontend source for every ``/analytics/codebase/<path>`` literal and
requires scope evidence beside each one that is not on a named exempt list.

Evidence, in the call's OWN statement -- the parenthesised call that holds the literal, not a window
of neighbouring lines: ``withSourceId(``, ``sourceIdQuery`` or an explicit ``source_id``; or
``scopeToSource: true`` together with ``requireSource: true`` in a file that injects ``withSourceId``
(``requireSource`` is what makes ``useFetchEndpoint`` skip a request that would answer 422). A task
factory (``useBackgroundTask`` / ``useTaskLoader``) names the base URL once and sends the source with
``start()`` / ``load()``, so it needs ``sourceIdQuery`` or ``source_id`` somewhere in its file.

Limits, stated: this reads text, not the call graph. A source held in a variable built elsewhere is
not in the statement, so it is flagged; the one such caller left is named in ``DEFERRED_CALLERS``.
The backend route guard (``routes_require_source_20513_test``) is the check that no route can be
called without a source at all.
"""

from __future__ import annotations

import re

import pytest
from repo_tests._analytics_routes_20513 import CROSS_SOURCE_PATHS, DEFERRED_CALLERS, DEFERRED_TO_PR2, OPS_SUFFIXES
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared.testfile_names import is_test_filename
from tools.lint._comment_syntax import code_lines
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

FRONTEND_SRC = "autobot-frontend/src"
MIN_SITES_EXAMINED = 30

#: ``/analytics/codebase/<path>`` (group 1 is ``<path>``), and the routes outside it that also require a source:
#: ``/reporting`` ``report`` / ``summary`` and ``/code-intelligence`` ``security/score/cached`` / ``analyze``
#: (group 1 is the whole path from ``reporting/`` / ``code-intelligence/``; #21463).
LITERAL = re.compile(
    r"(?:/api|\$\{getApiBase\(\)\})/(?:analytics/codebase/|(?=reporting/(?:report|summary)\b)"
    r"|(?=code-intelligence/security/score/(?:cached|analyze)\b))([A-Za-z0-9_\-/{}$.]+)"
)
#: A constant that holds one source-required route's literal: its USES are the call sites, its definition is not.
ROUTE_CONSTANTS = {"CACHED_SECURITY_SCORE_PATH": "code-intelligence/security/score/cached"}
_CONSTANT_USE = re.compile(r"\b(" + "|".join(ROUTE_CONSTANTS) + r")\b")
_CONSTANT_DEFINITION = re.compile(r"^\s*(?:export\s+)?const\s+(?:" + "|".join(ROUTE_CONSTANTS) + r")\b")
EVIDENCE = re.compile(r"withSourceId\(|sourceIdQuery|source_id")
SCOPE_FLAG = re.compile(r"scopeToSource:\s*true")
REQUIRE_FLAG = re.compile(r"requireSource:\s*true")
TASK_FACTORY = re.compile(r"use(?:BackgroundTask|TaskLoader)\b")
#: Source management: ``/sources/{id}...`` and ``/index/queue/{id}`` carry the source as a path parameter.
PATH_PARAM_PREFIXES = ("sources/", "index/queue/")
PR2_REASON = "#20513 PR 2"


def _normalise(raw: str) -> str:
    """``sources/${id}/sync?x=1`` -> ``sources/{x}/sync``."""
    return re.sub(r"\$\{[^}]*\}", "{x}", raw.split("?")[0]).rstrip("/")


def _route_sites(line: str) -> list[tuple[str, int]]:
    """``(route, column)`` for each source-required route *line* names: a literal, or a constant holding one."""
    if _CONSTANT_DEFINITION.match(line):
        return []  # the definition names the route once; the places that use it are the calls
    sites = [(_normalise(m.group(1)), m.start()) for m in LITERAL.finditer(line)]
    return sites + [(ROUTE_CONSTANTS[m.group(1)], m.start()) for m in _CONSTANT_USE.finditer(line)]


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


def _call_span(text: str, position: int) -> str:
    """The parenthesised call that holds *position*; the whole line when it sits in none.

    Walks out from the literal to the nearest unmatched ``(`` and on to its ``)``. Parentheses inside
    string literals are rare in these call sites and balanced when they occur (``${getApiBase()}``).
    """
    depth, start = 0, None
    for i in range(position - 1, -1, -1):
        char = text[i]
        if char == ")":
            depth += 1
        elif char == "(":
            if depth == 0:
                start = i
                break
            depth -= 1
    if start is None:
        line_start = text.rfind("\n", 0, position) + 1
        line_end = text.find("\n", position)
        return text[line_start : len(text) if line_end < 0 else line_end]
    while start > 0 and (text[start - 1].isalnum() or text[start - 1] in "_$."):
        start -= 1  # the callee's name is part of the statement: ``withSourceId(`` is evidence
    depth = 0
    for j in range(text.index("(", start), len(text)):
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth == 0:
                return text[start : j + 1]
    return text[start:]


def _code_by_line(text: str, filename: str) -> dict[int, str]:
    """Line number -> code text. Comments, whole-line and trailing, are not code: neither a call in one nor a source named in one counts."""
    return {entry.lineno: entry.text for entry in code_lines(text, name=filename or "scan.ts", strip_trailing=True)}


def _deferred_entry(deferred, filename: str, path: str, statement: str):
    """The exemption entry covering this call (same file and route, anchor inside its statement), or ``None``."""
    return next((e for e in deferred if e[:2] == (filename, path) and e[2] in statement), None)


def _has_scope_evidence(statement: str, preceding: str, file_scopes: bool, file_has_source: bool) -> bool:
    """Whether the call's own statement (or, for a task factory, its file) shows the source being sent."""
    if EVIDENCE.search(statement):
        return True
    if SCOPE_FLAG.search(statement) and REQUIRE_FLAG.search(statement) and file_scopes:
        return True
    return bool(TASK_FACTORY.search(preceding)) and file_has_source


def scan_text(
    text: str,
    filename: str = "",
    deferred: frozenset[tuple[str, str, str]] = DEFERRED_CALLERS,
    used: set[tuple[str, str, str]] | None = None,
) -> tuple[int, list[str]]:
    """``(sites examined, violations)`` for one file's text; *deferred* is the exemption set in force.

    An entry is ``(file, route, anchor)`` and covers only a call that would otherwise FAIL and whose
    own statement holds *anchor*; the entries it consumed are added to *used*.
    """
    lines = text.splitlines()
    code_text_by_line = _code_by_line(text, filename)
    code = "\n".join(code_text_by_line.values())
    file_scopes, file_has_source = "withSourceId" in code, bool(EVIDENCE.search(code))
    examined, violations, offset = 0, [], 0
    for index, line in enumerate(lines):
        line_offset, offset = offset, offset + len(line) + 1
        if index + 1 not in code_text_by_line:
            continue
        line = code_text_by_line[index + 1]
        for path, column in _route_sites(line):
            if _exempt(path):
                continue
            statement = _call_span(text, line_offset + column)
            preceding = "\n".join(lines[max(0, index - 2) : index + 1])
            ok = _has_scope_evidence(statement, preceding, file_scopes, file_has_source)
            entry = _deferred_entry(deferred, filename, path, statement)
            if not ok and entry:
                if used is not None:
                    used.add(entry)
                continue
            examined += 1
            if not ok:
                violations.append(f"line {index + 1}: {path}")
    return examined, violations


def _discover(root) -> list[str]:
    """Tracked frontend ``.ts`` / ``.vue`` sources (no tests, generated or typings); an empty tree yields ``[]``."""
    try:
        found = tracked_paths(root, FRONTEND_SRC)
    except EmptyEnumeration:
        return []
    skipped_dirs = {"node_modules", "generated", "__tests__"}
    return [
        p
        for p in found
        if p.endswith((".ts", ".vue"))
        and not p.endswith(".d.ts")
        and not is_test_filename(p)
        and not skipped_dirs & set(p.split("/"))
    ]


#: The frontend sources this scan reads (1262 measured at the base). A declaration new in this PR has no base
#: declaration to compute a floor from, so it pins ``floor=`` until it lands; the pin can go after merge (#19676).
REACH = declare(
    "analytics-callers-scope-to-source-20513",
    discover=_discover,
    what="frontend .ts/.vue sources",
    floor=1260,
    growth=400,
    roots=(FRONTEND_SRC,),
)


def test_every_scoped_analytics_call_sends_its_source():
    total, failures = 0, []
    files = REACH.examined(repo_root())
    for rel in files:
        examined, violations = scan_text((repo_root() / rel).read_text(encoding="utf-8"), rel)
        total += examined
        failures += [f"{rel}: {v}" for v in violations]
    REACH.completed(files, repo_root())
    assert total >= MIN_SITES_EXAMINED, f"only {total} call sites examined; the scan stopped seeing them"
    assert not failures, "analytics calls with no source_id (#20513):\n  " + "\n  ".join(failures)


def test_every_deferred_caller_entry_still_needs_its_exemption():
    """A STALE entry fails as loudly as a missing one: without it the call must still be a violation."""
    stale = []
    for entry in sorted(DEFERRED_CALLERS):
        rel, route, anchor = entry
        text = (repo_root() / rel).read_text(encoding="utf-8")
        used: set[tuple[str, str, str]] = set()
        scan_text(text, rel, deferred=frozenset({entry}), used=used)
        if entry not in used:  # no call holding the anchor still fails without scope evidence
            stale.append(f"{rel}: {route} ({anchor})")
    assert not stale, "DEFERRED_CALLERS entries the scan no longer needs (delete them):\n  " + "\n  ".join(stale)


def test_control_a_deferred_entry_covers_its_own_call_not_a_bare_one_before_it():
    entry = ("f.ts", "index", "_send(")
    bare = "await post('/api/analytics/codebase/index', a)\n"
    deferred_call = "await _send('/api/analytics/codebase/index', body)"
    used: set = set()
    assert scan_text(bare + deferred_call, "f.ts", deferred=frozenset({entry}), used=used)[1] == ["line 1: index"]
    assert used == {entry}


def test_control_a_deferred_call_that_gained_scope_leaves_its_entry_stale():
    entry = ("f.ts", "index", "_send(")
    text = "await post('/api/analytics/codebase/index', a)\nawait _send('/api/analytics/codebase/index', { source_id: id })"
    used: set = set()
    assert scan_text(text, "f.ts", deferred=frozenset({entry}), used=used)[1] == ["line 1: index"]
    assert used == set()  # the entry is unused, so the stale-entry test reports it


def test_control_a_trailing_comment_is_not_a_call():
    text = "const value = 1 // api.get('/api/analytics/codebase/stats')"
    assert scan_text(text, "f.ts") == (0, [])


def test_control_a_source_named_only_in_a_comment_is_not_evidence():
    factory = "const t = useTaskLoader(\n  `${getApiBase()}/analytics/codebase/analytics/import-tree`,\n  pick)"
    assert scan_text(factory + "\n// load(undefined, sourceIdQuery.value)")[1]
    assert scan_text(factory + "\nconst go = () => load(undefined, sourceIdQuery.value) // ok")[1] == []


def test_control_a_stale_deferred_entry_is_detected():
    scoped = "await post('/api/analytics/codebase/index', { source_id: id })"
    assert scan_text(scoped, "f.ts", deferred=frozenset())[1] == []  # needs no exemption: an entry here is stale
    bare = "await post('/api/analytics/codebase/index', body)"
    assert scan_text(bare, "f.ts", deferred=frozenset())[1] == ["line 1: index"]


def test_the_exempt_paths_are_the_shared_lists():
    assert _exempt("impact") == "cross-source"
    assert _exempt("patterns/tasks") == "cross-source"
    assert _exempt("index/cancel") == PR2_REASON
    assert _exempt("index/current") is None  # scoped now: a caller must send its source
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
        "useFetchEndpoint({ path: '/api/analytics/codebase/stats', scopeToSource: true, requireSource: true }, { withSourceId })",
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
            "/**",
            " * GET /api/analytics/codebase/stats",
            " */",
        ]
    )
    assert scan_text(text) == (0, [])


def test_control_a_task_factory_needs_the_source_sent_somewhere_in_its_file():
    factory = "const t = useTaskLoader(\n  `${getApiBase()}/analytics/codebase/analytics/import-tree`,\n  pick)"
    assert scan_text(factory)[1], "a factory whose file never sends a source is a bare call"
    assert scan_text(factory + "\nconst go = () => load(undefined, sourceIdQuery.value)")[1] == []


def test_control_a_scope_flag_without_the_injector_is_not_evidence():
    text = "useFetchEndpoint({ path: '/api/analytics/codebase/stats', scopeToSource: true, requireSource: true })"
    assert scan_text(text)[1], "scopeToSource alone sends nothing without withSourceId"


def test_control_a_scope_flag_without_require_source_is_not_evidence():
    text = "useFetchEndpoint({ path: '/api/analytics/codebase/stats', scopeToSource: true }, { withSourceId })"
    assert scan_text(text)[1], "without requireSource the call is still sent with no source and answers 422"


def test_control_evidence_must_be_in_the_calls_own_statement_not_a_neighbours():
    """The old 12-line window passed a bare call that sat beside a scoped one."""
    text = "\n".join(
        [
            "const a = await apiClient.get(withSourceId('/api/analytics/codebase/stats'))",
            "const b = await apiClient.get('/api/analytics/codebase/duplicates')",
        ]
    )
    examined, violations = scan_text(text)
    assert examined == 2 and violations == ["line 2: duplicates"]


def test_control_a_body_evidence_in_the_same_call_passes_and_one_outside_it_does_not():
    inside = "fetchWithAuth('/api/analytics/codebase/index', { body: JSON.stringify({ source_id: id }) })"
    outside = "const body = JSON.stringify({ source_id: id })\nfetchWithAuth('/api/analytics/codebase/index', { body })"
    assert scan_text(inside)[1] == []
    assert scan_text(outside)[1] == ["line 2: index"]
    deferred = outside.replace("fetchWithAuth(", "_sendIndexRequest(")
    assert scan_text(deferred, "autobot-frontend/src/composables/analytics/useIndexingJob.ts") == (0, [])
    assert scan_text(outside, "autobot-frontend/src/composables/analytics/useIndexingJob.ts")[
        1
    ], "the exemption covers only the anchored call"


REPORTING_FILE = "autobot-frontend/src/composables/analytics/useAnalyticsDataFetchers.ts"


def test_the_unified_report_caller_is_examined_and_skips_the_request_without_a_source():
    """#21463: ``/api/reporting/report`` requires a source; the caller must be seen by the scan and be scoped."""
    text = (repo_root() / REPORTING_FILE).read_text(encoding="utf-8")
    examined, violations = scan_text(text, REPORTING_FILE)
    reporting = text.count("/api/reporting/report")
    assert reporting >= 1, "the unified report caller moved; point this test at it"
    assert examined >= 1 and not violations, violations


@pytest.mark.parametrize(
    "snippet",
    [
        "useFetchEndpoint({ path: '/api/reporting/report', scopeToSource: true }, { withSourceId })",
        "apiClient.get('/api/reporting/summary')",
    ],
)
def test_control_a_reporting_call_without_a_skip_or_source_is_flagged(snippet):
    examined, violations = scan_text(snippet)
    assert examined == 1 and len(violations) == 1


def test_control_a_scoped_reporting_call_passes_and_an_optional_one_is_not_examined():
    scoped = "useFetchEndpoint({ path: '/api/reporting/report', scopeToSource: true, requireSource: true }, { withSourceId })"
    assert scan_text(scoped) == (1, [])
    assert scan_text("apiClient.get('/api/reporting/trends')") == (0, [])


CODE_INTEL_ROUTES = ("security/score/cached", "security/score/analyze")


@pytest.mark.parametrize("route", CODE_INTEL_ROUTES)
def test_control_a_bare_code_intelligence_source_route_is_flagged(route):
    for snippet in (
        f"apiClient.get('/api/code-intelligence/{route}')",
        f"post(`${{getApiBase()}}/code-intelligence/{route}`)",
    ):
        examined, violations = scan_text(snippet)
        assert examined == 1 and len(violations) == 1, snippet


@pytest.mark.parametrize("route", CODE_INTEL_ROUTES)
def test_control_a_scoped_code_intelligence_source_route_passes(route):
    assert scan_text(f"apiClient.get(withSourceId('/api/code-intelligence/{route}'))") == (1, [])


def test_control_code_intelligence_routes_that_take_a_path_not_a_source_are_not_examined():
    text = "\n".join(
        [
            "api.get('/api/code-intelligence/security/score')",
            "api.post('/api/code-intelligence/security/analyze', body)",
            "api.get(`${getApiBase()}/code-intelligence/security/score/status/${id}`)",
            "api.get('/api/code-intelligence/health-score')",
        ]
    )
    assert scan_text(text) == (0, [])


def test_control_a_use_of_the_cached_score_constant_is_a_call_and_its_definition_is_not():
    definition = "export const CACHED_SECURITY_SCORE_PATH = '/api/code-intelligence/security/score/cached'"
    assert scan_text(definition) == (0, [])
    bare = "useFetchEndpoint({ path: CACHED_SECURITY_SCORE_PATH, label: 'x' })"
    assert scan_text(bare) == (1, ["line 1: code-intelligence/security/score/cached"])
    scoped = "useFetchEndpoint({ path: CACHED_SECURITY_SCORE_PATH, scopeToSource: true, requireSource: true }, { withSourceId })"
    assert scan_text(scoped) == (1, [])


CACHED_READER = "autobot-frontend/src/composables/analytics/useCachedSecurityScore.ts"


def test_the_cached_score_reader_is_examined_and_skips_the_request_without_a_source():
    """#21463: the one reader of ``security/score/cached`` must be seen by the scan and be scoped."""
    text = (repo_root() / CACHED_READER).read_text(encoding="utf-8")
    examined, violations = scan_text(text, CACHED_READER)
    assert examined >= 1 and not violations, violations
