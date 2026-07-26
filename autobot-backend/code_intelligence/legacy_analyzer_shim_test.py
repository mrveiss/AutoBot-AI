# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Equivalence tests for the code_analysis.src legacy analyzer shims (#12362).

Verifies that ``code_analysis.src.performance_analyzer.PerformanceAnalyzer``
and ``code_analysis.src.security_analyzer.SecurityAnalyzer`` — now thin
adapters delegating to the canonical ``code_intelligence.performance_analysis``
/ ``code_intelligence.security`` packages — still return the legacy response
contract (dict shape + dataclass field names) that pre-existing callers
depend on, and that the type-divergence field mapping (``line_number`` from
``line_start``, string ``issue_type``/``vulnerability_type`` from the modern
enums) is correct.

Placed under code_intelligence/ (not code_analysis/src/) because
code_intelligence/conftest.py repairs the code_intelligence package's
__path__ so its real subpackages (performance_analysis, security) resolve —
the shims under test import from those subpackages, and the top-level
conftest's generic code_intelligence stub (used everywhere else to avoid the
heavy __init__ chain) does not carry a working __path__.
"""

import tempfile
import textwrap

import pytest

from code_analysis.src.performance_analyzer import (
    PerformanceAnalyzer,
    PerformanceIssue,
    PerformanceRecommendation,
)
from code_analysis.src.security_analyzer import (
    SecurityAnalyzer,
    SecurityVulnerability,
)


class TestPerformanceShimFieldMapping:
    """Verify the legacy PerformanceIssue shape is populated correctly."""

    @pytest.mark.asyncio
    async def test_analyze_performance_response_shape(self, tmp_path):
        """analyze_performance() must keep the legacy aggregate dict shape."""
        (tmp_path / "blocking.py").write_text(
            textwrap.dedent(
                """
                import time

                async def blocked():
                    time.sleep(5)
                """
            )
        )

        analyzer = PerformanceAnalyzer()
        results = await analyzer.analyze_performance(root_path=str(tmp_path))

        for key in (
            "total_performance_issues",
            "categories",
            "critical_issues",
            "high_priority_issues",
            "recommendations_count",
            "analysis_time_seconds",
            "performance_details",
            "optimization_recommendations",
            "metrics",
        ):
            assert key in results

        assert results["total_performance_issues"] >= 1
        assert results["critical_issues"] >= 1

    @pytest.mark.asyncio
    async def test_field_mapping_line_number_and_issue_type(self, tmp_path):
        """line_number must come from the modern line_start; issue_type must be a legacy bucket string."""
        (tmp_path / "blocking.py").write_text(
            textwrap.dedent(
                """
                import time

                async def blocked():
                    time.sleep(5)
                """
            )
        )

        analyzer = PerformanceAnalyzer()
        results = await analyzer.analyze_performance(root_path=str(tmp_path))

        details = results["performance_details"]
        assert len(details) >= 1
        # time.sleep() in async -> modern SYNC_IN_ASYNC/CRITICAL -> legacy
        # "blocking_calls" bucket (see _LEGACY_BUCKET_BY_ISSUE_TYPE).
        sleep_issue = next(d for d in details if "time.sleep" in d["description"])
        assert sleep_issue["type"] == "blocking_calls"
        assert sleep_issue["severity"] == "critical"
        assert sleep_issue["line"] == 5  # matches modern line_start for this fixture

    @pytest.mark.asyncio
    async def test_dataclass_field_names_unchanged(self, tmp_path):
        """PerformanceIssue must keep line_number/issue_type (not line_start/PerformanceIssueType)."""
        (tmp_path / "leak.py").write_text('f = open("x.txt", "r")\ndata = f.read()\n')

        analyzer = PerformanceAnalyzer()
        results = await analyzer.analyze_performance(root_path=str(tmp_path))

        # Reconstruct one PerformanceIssue directly to assert the dataclass contract.
        issue = PerformanceIssue(
            file_path="x.py",
            line_number=1,
            function_name=None,
            issue_type="memory_leaks",
            description="d",
            severity="medium",
            code_snippet="c",
            suggestion="s",
            estimated_impact="medium",
        )
        assert issue.line_number == 1
        assert issue.issue_type == "memory_leaks"
        assert results["total_performance_issues"] >= 1


class TestPerformanceShimRecommendations:
    """Verify PerformanceRecommendation objects are still produced."""

    @pytest.mark.asyncio
    async def test_recommendations_generated_for_high_impact(self, tmp_path):
        (tmp_path / "blocking.py").write_text(
            textwrap.dedent(
                """
                import time

                async def blocked():
                    time.sleep(5)
                """
            )
        )

        analyzer = PerformanceAnalyzer()
        results = await analyzer.analyze_performance(root_path=str(tmp_path))

        assert results["recommendations_count"] >= 1
        rec = results["optimization_recommendations"][0]
        for key in ("category", "title", "description", "affected_files", "priority", "code_examples"):
            assert key in rec


class TestSecurityShimFieldMapping:
    """Verify the legacy SecurityVulnerability shape is populated correctly."""

    @pytest.mark.asyncio
    async def test_analyze_security_response_shape(self, tmp_path):
        """analyze_security() must keep the legacy aggregate dict shape."""
        (tmp_path / "sqli.py").write_text(
            textwrap.dedent(
                """
                def get_user(cursor, user_id):
                    cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
                    return cursor.fetchone()
                """
            )
        )

        analyzer = SecurityAnalyzer()
        results = await analyzer.analyze_security(root_path=str(tmp_path))

        for key in (
            "total_vulnerabilities",
            "categories",
            "critical_vulnerabilities",
            "high_severity_count",
            "recommendations_count",
            "analysis_time_seconds",
            "vulnerability_details",
            "security_recommendations",
            "metrics",
        ):
            assert key in results

        assert results["total_vulnerabilities"] >= 1
        assert results["critical_vulnerabilities"] >= 1

    @pytest.mark.asyncio
    async def test_field_mapping_line_number_and_vulnerability_type(self, tmp_path):
        """line_number must come from the modern line_start; vulnerability_type must be a legacy bucket string."""
        (tmp_path / "sqli.py").write_text(
            textwrap.dedent(
                """
                def get_user(cursor, user_id):
                    cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
                    return cursor.fetchone()
                """
            )
        )

        analyzer = SecurityAnalyzer()
        results = await analyzer.analyze_security(root_path=str(tmp_path))

        details = results["vulnerability_details"]
        assert len(details) >= 1
        sqli = next(d for d in details if d["type"] == "sql_injection")
        assert sqli["severity"] == "critical"
        assert sqli["cwe_id"] == "CWE-89"
        assert sqli["line"] == 3  # matches modern line_start for this fixture

    @pytest.mark.asyncio
    async def test_dataclass_field_names_unchanged(self):
        """SecurityVulnerability must keep line_number/vulnerability_type (not line_start/VulnerabilityType)."""
        vuln = SecurityVulnerability(
            file_path="x.py",
            line_number=1,
            function_name=None,
            vulnerability_type="sql_injection",
            severity="critical",
            description="d",
            code_snippet="c",
            cwe_id="CWE-89",
            fix_suggestion="s",
            confidence=0.9,
        )
        assert vuln.line_number == 1
        assert vuln.vulnerability_type == "sql_injection"


class TestLegacyBucketMappingCompleteness:
    """Every canonical enum member must have a deliberate legacy-bucket mapping.

    Guards against silent drift: if code_intelligence adds a new
    PerformanceIssueType/VulnerabilityType member without updating the shim's
    mapping table, this test fails loudly instead of the new type silently
    falling into the shim's fallback bucket.
    """

    def test_performance_issue_type_mapping_is_exhaustive(self):
        from code_analysis.src.performance_analyzer import _LEGACY_BUCKET_BY_ISSUE_TYPE
        from code_intelligence.performance_analysis import PerformanceIssueType

        missing = set(PerformanceIssueType) - set(_LEGACY_BUCKET_BY_ISSUE_TYPE)
        assert missing == set(), f"New PerformanceIssueType member(s) need a legacy bucket mapping: {missing}"

    def test_vulnerability_type_mapping_is_exhaustive(self):
        from code_analysis.src.security_analyzer import _LEGACY_BUCKET_BY_VULN_TYPE
        from code_intelligence.security import VulnerabilityType

        missing = set(VulnerabilityType) - set(_LEGACY_BUCKET_BY_VULN_TYPE)
        assert missing == set(), f"New VulnerabilityType member(s) need a legacy bucket mapping: {missing}"


class TestPerformanceRecommendationDataclass:
    """Sanity-check the standalone dataclasses still construct as before."""

    def test_recommendation_construction(self):
        rec = PerformanceRecommendation(
            category="blocking_calls",
            title="t",
            description="d",
            affected_files=["a.py"],
            priority="high",
            code_examples=[],
        )
        assert rec.category == "blocking_calls"
        assert rec.priority == "high"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
