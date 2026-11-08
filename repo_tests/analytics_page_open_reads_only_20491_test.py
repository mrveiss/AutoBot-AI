# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Opening Codebase Analytics starts no scan (#20491).

The page-open path may only read stored results, so what it calls is an allow-list: a new loader
has to be added here knowingly. ``COMPUTING`` compute at least on a cache miss, and an explicit run
must still reach them. All of it is read from the source because the page's mount pulls in far more
than a unit test can stub, and the failure this guards against is one line added back to one list.
"""

from __future__ import annotations

import re

from repo_tests._paths import repo_root

ANALYTICS = "autobot-frontend/src/components/analytics/CodebaseAnalytics.vue"
FETCHERS = "autobot-frontend/src/composables/analytics/useAnalyticsDataFetchers.ts"
LOADERS = "autobot-frontend/src/composables/analytics/useDashboardLoaders.ts"
JOB = "autobot-frontend/src/composables/analytics/useIndexingJob.ts"
MOUNT_ALLOWED = {
    "checkCurrentIndexingJob",
    "loadCachedAnalyticsData",
    "loadCodeQuality",
    "loadCommunicationPatterns",
    "loadPerformanceMetrics",
    "loadProjectRepoMap",
    "loadSourceById",
    "loadSources",
    "loadSystemOverview",
}
SCAN_ALLOWED = {"getCrossLanguageAnalysis", "loadCachedBugPrediction", "loadCachedSecurityScore"}
COMPUTING = (
    "loadConfigDuplicates",
    "loadApiEndpointAnalysis",
    "loadPerformanceScore",
    "loadRedisHealth",
    "loadEnvironmentAnalysis",
    "loadOwnershipAnalysis",
    "runCodeIntelligenceAnalysis",
)


def _read(rel: str) -> str:
    return (repo_root() / rel).read_text(encoding="utf-8")


def page_open_scans(source: str) -> str:
    """The body of the scan list the page runs when it opens."""
    match = re.search(r"const codeIntelExtraScans = .*?\n\]\n", source, re.DOTALL)
    assert match, "the page-open scan list moved; point this guard at it"
    return match.group(0)


def mount_calls(source: str) -> set[str]:
    """The functions ``onMounted`` calls directly, by name."""
    opening = "onMounted(async () => {"
    body = source[source.index(opening) + len(opening) :].split("\n})\n", 1)[0]
    return set(re.findall(r"^\s*(?:await |void )?(\w+)\(", body, re.MULTILINE))


def scan_calls(source: str) -> set[str]:
    """The loaders named in the page-open scan list."""
    return set(re.findall(r"await (\w+)\(", page_open_scans(source)))


def test_the_detectors_read_what_they_mean() -> None:
    planted = "const codeIntelExtraScans = (): X[] => [\n  { run: async () => { await loadRedisHealth() } },\n]\nloadOther()\n"
    assert scan_calls(planted) == {"loadRedisHealth"}
    mounted = "onMounted(async () => {\n  void a()\n  await b()\n  c()\n  if (d) {\n    x.y()\n  }\n})\nz()\n"
    assert mount_calls(mounted) == {"a", "b", "c"}


def test_page_open_calls_only_what_reads() -> None:
    source = _read(ANALYTICS)
    assert mount_calls(source) - MOUNT_ALLOWED == set(), "only an explicit run may start a scan"
    assert scan_calls(source) - SCAN_ALLOWED == set(), "only an explicit run may start a scan"


def test_the_overview_queues_no_task() -> None:
    assert "useBackgroundTask" not in _read(LOADERS), "the overview's POST queues a task on every page open"


def test_an_explicit_run_still_calls_them() -> None:
    source = _read(ANALYTICS)
    full = source[source.index("const codeIntelFullScans") :]
    for loader in COMPUTING:
        assert loader in full, f"{loader} is no longer reachable from an explicit run"
    assert "onIndexComplete: () => runAllAnalysisScans(codeIntelFullScans())" in source


def test_the_call_graph_needs_an_explicit_run() -> None:
    assert re.search(r"useFullScans\s*\?\s*\[\{ id: 'callgraph'", _read(FETCHERS))


def test_the_dashboard_reads_cached_duplicates() -> None:
    source = _read(LOADERS)
    assert "'/api/analytics/codebase/duplicates/cached'" in source
    assert "'/api/analytics/codebase/duplicates'," not in source


def test_both_readers_of_the_current_job_check_its_source() -> None:
    source = _read(JOB)
    for reader in ("const checkCurrentIndexingJob", "const pollJobStatus"):
        body = source[source.index(reader) :]
        body = body[: body.index("\n  }\n")]
        assert "jobBelongsToSource(data.source_id" in body, reader


SCORES = "autobot-frontend/src/composables/analytics/useCodeIntelScores.ts"
INTELLIGENCE = "autobot-frontend/src/composables/useCodeIntelligence.ts"


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", text)


def _block(source: str, start: str, end: str) -> str:
    assert start in source, f"split marker moved: {start!r}"
    return source[source.index(start) :].split(end, 1)[0]


def sends_its_source(block: str) -> bool:
    """True when the block scopes the read to a source (option set to true, scoper passed)."""
    code = _strip_comments(block)
    return bool(re.search(r"scopeToSource:\s*true", code)) and "{ withSourceId }" in code


def scoped_by_with_source_id(block: str) -> bool:
    """True when the block builds its URL through ``withSourceId(...)``."""
    return bool(re.search(r"withSourceId\(", _strip_comments(block)))


def test_the_source_detectors_fail_without_the_scoping() -> None:
    real = _block(_read(SCORES), "const cachedSecurityScoreEndpoint", "const loadCachedSecurityScore")
    assert sends_its_source(real), "control: the real block is scoped"
    assert not sends_its_source(real.replace("scopeToSource: true", "scopeToSource: false"))
    assert not sends_its_source(real.replace("{ withSourceId }", "{}"))
    assert not sends_its_source("// scopeToSource: true { withSourceId }\npath: 'x'")
    cached = _block(_read(INTELLIGENCE), "async function getSecurityScoreCached", "\n  }\n")
    assert scoped_by_with_source_id(cached), "control: the real read is scoped"
    assert not scoped_by_with_source_id(cached.replace("withSourceId(", "noop("))
    assert not scoped_by_with_source_id("// withSourceId(url)\nget(url)")


def test_the_cached_security_read_sends_its_source() -> None:
    """The route requires ``source_id``; without it the page-open read answers 422."""
    block = _block(_read(SCORES), "const cachedSecurityScoreEndpoint", "const loadCachedSecurityScore")
    assert sends_its_source(block)


def test_the_other_cached_security_read_sends_its_source() -> None:
    block = _block(_read(INTELLIGENCE), "async function getSecurityScoreCached", "\n  }\n")
    assert scoped_by_with_source_id(block)
