# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#14988 — two severity-literal shapes the dict-entry ratchet cannot see.

``enum_union_guard_test.py``'s ``_SEVERITY_LITERAL`` matches only
``"severity": "<literal>"``. Two other shapes carry the same defect —
``severity = "<literal>"`` and ``severity == "<literal>"`` — and were
unratcheted, so #13597/#14956's conversion work could regrow through either
without anything going red. This is a second file, not more tests appended
to ``enum_union_guard_test.py``: that file is grandfathered at its current
line count in ``python_file_size_known_large.py`` and may not grow.

Measured on `Dev_new_gui` after #14988 landed: 167 hits across 48 files (the
issue's own count of 219/55 was taken before other work already converted
some — re-measure, do not trust the issue body). Four values found in that
167 — ``none``, ``moderate``, ``missing``, ``forbidden`` — are NOT canonical
``Severity`` vocabulary; see ``DELIBERATE_DIFFERENT_DOMAIN_FILES`` below for
why, decided in #14988 so the next reader does not re-litigate it per file.

The remaining 167 are grandfathered debt, not accepted as permanent: #15400
tracks converting each of ``KNOWN_UNCONVERTED_SEVERITY_LITERAL_FILES`` to
``autobot_shared.status_enums.Severity`` or moving it to a deliberate
allowlist, the same choice #14956 already made for the dict shape.
"""

from __future__ import annotations

import functools
import re
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Same shapes #14988 measured. No word boundary before ``severity`` is
# deliberate: it is the shape the issue specified and ground-truthed against.
_SEVERITY_KEYWORD_LITERAL = re.compile(r"""severity\s*=\s*["'][A-Za-z_]+["']""")
_SEVERITY_COMPARISON_LITERAL = re.compile(r"""severity["']?\]?\s*==\s*["'][A-Za-z_]+["']""")

# Whole files excluded from the ratchet entirely — not grandfathered debt,
# because the field named "severity" here is a DIFFERENT vocabulary, and
# converting it to Severity would be wrong rather than merely deferred.
# Decided in #14988; see that issue for the per-value evidence.
DELIBERATE_DIFFERENT_DOMAIN_FILES = {
    # DeltaResult.severity is a 3-value metric-delta scale (none/moderate/
    # critical), not the Severity ladder — "critical" coincides, "none" and
    # "moderate" (as a distinct-domain spelling) do not exist as such there.
    "autobot_shared/delta_engine.py",
    "autobot_shared/delta_engine_test.py",
    # DriftItem.severity is a drift-TYPE taxonomy (missing/type_mismatch/
    # unknown), not a severity scale. The field is misnamed; that is a
    # separate, narrower rename issue, not this one.
    "autobot_shared/env_drift_detector.py",
    # The local `severity` variable here carries CommandRisk's vocabulary
    # (high/critical/forbidden), not Severity's, under a misleading name.
    "autobot-backend/security/command_patterns.py",
    "autobot-backend/security/command_patterns_test.py",
}

# Grandfathered debt (#15400): converting every one of these needs the same
# in-process-producer-vs-external-boundary judgment #14956 applied to the
# dict shape. Never add to this list — a literal appearing in a NEW file is
# a regression, not more debt to grandfather.
KNOWN_UNCONVERTED_SEVERITY_LITERAL_FILES = {
    "autobot-backend/agents/development_speedup_agent.py",
    "autobot-backend/api/analytics_cfg.py",
    "autobot-backend/api/analytics_log_patterns.py",
    "autobot-backend/api/analytics_quality.py",
    "autobot-backend/api/codebase_analytics/analyzers.py",
    "autobot-backend/api/codebase_analytics/codebase_stats_endpoint_test.py",
    "autobot-backend/api/codebase_analytics/endpoints/dependencies.py",
    "autobot-backend/api/codebase_analytics/technical_debt_detection_test.py",
    "autobot-backend/api/knowledge_grounding_conflicts_decode_test.py",
    "autobot-backend/api/monitoring.py",
    "autobot-backend/code_analysis/scripts/analyze_code_quality.py",
    "autobot-backend/code_analysis/scripts/analyze_env_vars.py",
    "autobot-backend/code_analysis/scripts/analyze_frontend.py",
    "autobot-backend/code_analysis/scripts/analyze_performance.py",
    "autobot-backend/code_analysis/src/api_consistency_analyzer.py",
    "autobot-backend/code_analysis/src/architectural_analysis/issue_detector.py",
    "autobot-backend/code_analysis/src/code_quality_dashboard.py",
    "autobot-backend/code_analysis/src/env_analyzer.py",
    "autobot-backend/code_analysis/src/frontend_analyzer.py",
    "autobot-backend/code_analysis/src/patch_generator.py",
    "autobot-backend/code_analysis/src/performance_analyzer.py",
    "autobot-backend/code_analysis/src/remediation_loop_test.py",
    "autobot-backend/code_analysis/src/security_analyzer.py",
    "autobot-backend/code_analysis/src/testing_coverage_analyzer.py",
    "autobot-backend/code_intelligence/anti_pattern_detector_test.py",
    "autobot-backend/code_intelligence/code_evolution_miner_test.py",
    "autobot-backend/code_intelligence/code_fingerprinting_test.py",
    "autobot-backend/code_intelligence/code_review_engine_test.py",
    "autobot-backend/code_intelligence/conversation_analysis/analyzer.py",
    "autobot-backend/code_intelligence/conversation_flow_analyzer_test.py",
    "autobot-backend/code_intelligence/legacy_analyzer_shim_test.py",
    "autobot-backend/config/ssot_mappings.py",
    "autobot-backend/context_aware_decision/tests/test_counterfactual_reasoner.py",
    "autobot-backend/llc/tests/test_finding_proposal_service.py",
    "autobot-backend/llc/tests/test_findings_api.py",
    "autobot-backend/llc/tests/test_findings_gather.py",
    "autobot-backend/llc/tests/test_findings_policy.py",
    "autobot-backend/monitoring/alertmanager_webhook_test.py",
    "autobot-backend/orchestration/capability_audit.py",
    "autobot-backend/orchestration/capability_audit_test.py",
    "autobot-backend/security/enterprise/threat_detection/analyzers/command_injection.py",
    "autobot-backend/services/grounded_agent.py",
    "autobot-backend/services/security_memory_integration_test.py",
    "autobot-backend/services/security_tool_parsers_test.py",
    "autobot-backend/services/security_workflow_manager_test.py",
    "autobot-backend/tests/services/test_causal_inference_engine.py",
    "autobot-backend/utils/error_metrics.py",
    "autobot_shared/monitoring/metrics/cgroup_memory_test.py",
}

# #15400 filed this at 167. Lower as literals convert; never raise it.
SEVERITY_SHAPE_LITERAL_CEILING = 167

# Floor, set under the ceiling for the same reason the dict-shape ratchet
# uses one: converting one of the grandfathered entries is a deliberate edit
# of this guard, not silent drift the ratchet fails to notice either way.
SEVERITY_SHAPE_LITERAL_FLOOR = 160

# Floor for the tracked-file enumeration itself — an empty walk must not
# read as "nothing to convert".
_TRACKED_PY_FLOOR = 3000


@functools.lru_cache(maxsize=1)
def _tracked_python_files() -> tuple[str, ...]:
    out = subprocess.run(  # nosec B603  # fixed argv, no shell
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return tuple(line for line in out.stdout.splitlines() if line)


def _shape_literal_hits() -> list[tuple[str, str]]:
    """(file, matched text) for every keyword- or comparison-shaped literal."""
    hits = []
    for rel in _tracked_python_files():
        if not (rel.startswith("autobot-backend/") or rel.startswith("autobot_shared/")):
            continue
        if rel in DELIBERATE_DIFFERENT_DOMAIN_FILES:
            continue
        try:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        except OSError:
            continue
        for pattern in (_SEVERITY_KEYWORD_LITERAL, _SEVERITY_COMPARISON_LITERAL):
            hits.extend((rel, match.group(0)) for match in pattern.finditer(text))
    return hits


def test_the_enumeration_reaches_the_repo():
    """Guards every scan below: an empty file list agrees with anything."""
    assert len(_tracked_python_files()) >= _TRACKED_PY_FLOOR


def _banned_shape(shape: str, quote: str, value: str) -> str:
    """Build a matching string without spelling one out in this guard's own source."""
    key = quote + value + quote
    if shape == "keyword":
        return "severity = " + key
    return "severity == " + key


def test_the_shape_matchers_still_match():
    assert _SEVERITY_KEYWORD_LITERAL.search(_banned_shape("keyword", '"', "high"))
    assert _SEVERITY_COMPARISON_LITERAL.search(_banned_shape("comparison", "'", "critical"))
    assert not _SEVERITY_KEYWORD_LITERAL.search("severity = Severity.HIGH.value")
    assert not _SEVERITY_COMPARISON_LITERAL.search("severity == Severity.CRITICAL.value")


def test_this_guard_does_not_trip_its_own_matcher():
    """``repo_tests/`` is outside the scanned roots, but assert it anyway."""
    source = Path(__file__).read_text(encoding="utf-8")
    assert not _SEVERITY_KEYWORD_LITERAL.search(source)
    assert not _SEVERITY_COMPARISON_LITERAL.search(source)


def test_shape_literals_do_not_grow():
    hits = _shape_literal_hits()
    assert len(hits) >= SEVERITY_SHAPE_LITERAL_FLOOR, (
        f"#15400: only {len(hits)} keyword/comparison severity literals found "
        f"(floor {SEVERITY_SHAPE_LITERAL_FLOOR}) — a broken matcher or a moved "
        f"root, not a clean tree. If genuinely converted, drop the file from "
        f"KNOWN_UNCONVERTED_SEVERITY_LITERAL_FILES and lower both bounds together."
    )
    assert len(hits) <= SEVERITY_SHAPE_LITERAL_CEILING, (
        f"#14988/#15400: keyword/comparison severity literals grew to {len(hits)} "
        f"(ceiling {SEVERITY_SHAPE_LITERAL_CEILING}). Use "
        "autobot_shared.status_enums.Severity, or if the field is a different "
        "vocabulary add the file to DELIBERATE_DIFFERENT_DOMAIN_FILES with why."
    )


def test_no_new_file_carries_a_shape_literal():
    """The ceiling alone would let one file shed a literal while another gained one."""
    offenders = {rel for rel, _ in _shape_literal_hits()}
    assert offenders, "matcher reached nothing — broken matcher, not a clean tree"
    unexpected = offenders - KNOWN_UNCONVERTED_SEVERITY_LITERAL_FILES
    assert not unexpected, (
        f"#15400: keyword/comparison severity literals appeared in a file not "
        f"already grandfathered: {sorted(unexpected)}. Convert it to "
        "autobot_shared.status_enums.Severity, or add it to "
        "KNOWN_UNCONVERTED_SEVERITY_LITERAL_FILES with a #15400 sub-task."
    )


def test_every_grandfathered_file_still_has_a_literal():
    """A stale entry exempts nothing while looking like tracked debt."""
    offenders = {rel for rel, _ in _shape_literal_hits()}
    stale = KNOWN_UNCONVERTED_SEVERITY_LITERAL_FILES - offenders
    assert not stale, (
        f"#15400: these files no longer carry a keyword/comparison severity "
        f"literal — remove them from KNOWN_UNCONVERTED_SEVERITY_LITERAL_FILES: "
        f"{sorted(stale)}"
    )


def test_every_deliberate_different_domain_file_still_exists():
    """An allowlist entry naming a moved/deleted file exempts nothing."""
    for rel in DELIBERATE_DIFFERENT_DOMAIN_FILES:
        assert (REPO_ROOT / rel).exists(), f"#14988: {rel} is gone — the exemption has no target"
