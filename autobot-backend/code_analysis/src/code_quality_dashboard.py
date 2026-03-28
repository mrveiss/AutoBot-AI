"""
Comprehensive Code Quality Dashboard
Integrates all analyzers: duplicates, environment variables, performance, security, API consistency, testing coverage, and architectural patterns
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from api_consistency_analyzer import APIConsistencyAnalyzer
from architectural_pattern_analyzer import ArchitecturalPatternAnalyzer
from code_analyzer import CodeAnalyzer
from env_analyzer import EnvironmentVariableAnalyzer
from performance_analyzer import PerformanceAnalyzer
from security_analyzer import SecurityAnalyzer
from testing_coverage_analyzer import TestingCoverageAnalyzer

from autobot_shared.redis_client import get_redis_client
from config import UnifiedConfig

# Initialize unified config
config = UnifiedConfig()
logger = logging.getLogger(__name__)


@dataclass
class QualityMetrics:
    """Overall code quality metrics"""

    overall_score: float  # 0-100
    code_duplication_score: float
    environment_config_score: float
    performance_score: float
    security_score: float
    api_consistency_score: float
    test_coverage_score: float
    architecture_score: float
    maintainability_index: float
    technical_debt_ratio: float


@dataclass
class QualityIssue:
    """Represents a code quality issue"""

    category: str  # duplication, security, performance, etc.
    severity: str  # critical, high, medium, low
    title: str
    description: str
    file_path: str
    line_number: int
    fix_suggestion: str
    estimated_effort: str  # low, medium, high
    priority_score: int  # 1-100


@dataclass
class QualityTrend:
    """Quality trend over time"""

    timestamp: datetime
    overall_score: float
    issue_count: int
    critical_issues: int
    files_analyzed: int


class CodeQualityDashboard:
    """Comprehensive code quality dashboard"""

    def __init__(self, redis_client=None):
        self.redis_client = redis_client or get_redis_client(async_client=True)
        self.config = config

        # Initialize all analyzers
        self.code_analyzer = CodeAnalyzer(self.redis_client)
        self.env_analyzer = EnvironmentVariableAnalyzer(self.redis_client)
        self.performance_analyzer = PerformanceAnalyzer(self.redis_client)
        self.security_analyzer = SecurityAnalyzer(self.redis_client)
        self.api_analyzer = APIConsistencyAnalyzer(self.redis_client)
        self.testing_analyzer = TestingCoverageAnalyzer(self.redis_client)
        self.architecture_analyzer = ArchitecturalPatternAnalyzer(self.redis_client)

        # Caching keys
        self.DASHBOARD_KEY = "code_quality:dashboard"
        self.TRENDS_KEY = "code_quality:trends"
        self.ISSUES_KEY = "code_quality:issues"

        logger.info("Code Quality Dashboard initialized with all analyzers")

    async def _gather_analysis_results(
        self, root_path: str, patterns: List[str]
    ) -> Dict[str, Any]:
        """Run all analyses in parallel and return results dict. Issue #1183."""
        analyses = await asyncio.gather(
            self._run_duplication_analysis(root_path, patterns),
            self._run_environment_analysis(root_path, patterns),
            self._run_performance_analysis(root_path, patterns),
            self._run_security_analysis(root_path, patterns),
            self._run_api_analysis(root_path, patterns),
            self._run_testing_analysis(root_path, patterns),
            self._run_architecture_analysis(root_path, patterns),
            return_exceptions=True,
        )
        keys = [
            "duplication",
            "environment",
            "performance",
            "security",
            "api_consistency",
            "testing_coverage",
            "architecture",
        ]
        return {
            k: (v if not isinstance(v, Exception) else None)
            for k, v in zip(keys, analyses)
        }

    def _build_report_dict(
        self,
        analysis_results: Dict[str, Any],
        quality_metrics: Any,
        all_issues: list,
        prioritized_issues: list,
        recommendations: list,
        technical_debt: dict,
        trend_data: list,
        analysis_time: float,
    ) -> Dict[str, Any]:
        """Assemble the final comprehensive report dictionary. Issue #1183."""
        qm = quality_metrics
        return {
            "timestamp": datetime.now().isoformat(),
            "analysis_time_seconds": analysis_time,
            "overall_quality_score": qm.overall_score,
            "quality_metrics": {
                "overall_score": qm.overall_score,
                "code_duplication_score": qm.code_duplication_score,
                "environment_config_score": qm.environment_config_score,
                "performance_score": qm.performance_score,
                "security_score": qm.security_score,
                "api_consistency_score": qm.api_consistency_score,
                "test_coverage_score": qm.test_coverage_score,
                "architecture_score": qm.architecture_score,
                "maintainability_index": qm.maintainability_index,
                "technical_debt_ratio": qm.technical_debt_ratio,
            },
            "issue_summary": {
                "total_issues": len(all_issues),
                "critical_issues": len(
                    [i for i in all_issues if i.severity == "critical"]
                ),
                "high_priority_issues": len(
                    [i for i in all_issues if i.severity == "high"]
                ),
                "medium_priority_issues": len(
                    [i for i in all_issues if i.severity == "medium"]
                ),
                "low_priority_issues": len(
                    [i for i in all_issues if i.severity == "low"]
                ),
                "by_category": self._group_issues_by_category(all_issues),
            },
            "detailed_analyses": analysis_results,
            "prioritized_issues": [
                self._serialize_issue(i) for i in prioritized_issues[:50]
            ],
            "improvement_recommendations": recommendations,
            "technical_debt": technical_debt,
            "quality_trends": trend_data,
            "files_analyzed": self._count_analyzed_files(analysis_results),
        }

    async def generate_comprehensive_report(
        self,
        root_path: str = ".",
        patterns: List[str] = None,
        include_trends: bool = True,
    ) -> Dict[str, Any]:
        """Generate comprehensive code quality report"""
        start_time = time.time()
        patterns = patterns or ["src/**/*.py", "backend/**/*.py"]
        logger.info("Starting comprehensive code quality analysis...")
        analysis_results = await self._gather_analysis_results(root_path, patterns)
        quality_metrics = self._calculate_quality_metrics(analysis_results)
        all_issues = self._extract_all_issues(analysis_results)
        prioritized_issues = self._prioritize_issues(all_issues)
        recommendations = self._generate_improvement_recommendations(
            analysis_results, prioritized_issues
        )
        technical_debt = self._calculate_technical_debt(prioritized_issues)
        analysis_time = time.time() - start_time
        trend_data = await self._get_quality_trends() if include_trends else []
        comprehensive_report = self._build_report_dict(
            analysis_results,
            quality_metrics,
            all_issues,
            prioritized_issues,
            recommendations,
            technical_debt,
            trend_data,
            analysis_time,
        )
        await self._save_quality_trend(quality_metrics, len(all_issues))
        await self._cache_dashboard_report(comprehensive_report)
        logger.info(
            f"Comprehensive code quality analysis complete in {analysis_time:.2f}s"
        )
        return comprehensive_report

    async def _run_duplication_analysis(
        self, root_path: str, patterns: List[str]
    ) -> Optional[Dict[str, Any]]:
        """Run code duplication analysis"""
        try:
            logger.info("Running duplication analysis...")
            return await self.code_analyzer.find_duplicates(root_path, patterns)
        except Exception as e:
            logger.error(f"Duplication analysis failed: {e}")
            return None

    async def _run_environment_analysis(
        self, root_path: str, patterns: List[str]
    ) -> Optional[Dict[str, Any]]:
        """Run environment variable analysis"""
        try:
            logger.info("Running environment variable analysis...")
            return await self.env_analyzer.analyze_environment_variables(
                root_path, patterns
            )
        except Exception as e:
            logger.error(f"Environment analysis failed: {e}")
            return None

    async def _run_performance_analysis(
        self, root_path: str, patterns: List[str]
    ) -> Optional[Dict[str, Any]]:
        """Run performance analysis"""
        try:
            logger.info("Running performance analysis...")
            return await self.performance_analyzer.analyze_performance(
                root_path, patterns
            )
        except Exception as e:
            logger.error(f"Performance analysis failed: {e}")
            return None

    async def _run_security_analysis(
        self, root_path: str, patterns: List[str]
    ) -> Optional[Dict[str, Any]]:
        """Run security analysis"""
        try:
            logger.info("Running security analysis...")
            return await self.security_analyzer.analyze_security(root_path, patterns)
        except Exception as e:
            logger.error(f"Security analysis failed: {e}")
            return None

    async def _run_api_analysis(
        self, root_path: str, patterns: List[str]
    ) -> Optional[Dict[str, Any]]:
        """Run API consistency analysis"""
        try:
            logger.info("Running API consistency analysis...")
            return await self.api_analyzer.analyze_api_consistency(root_path, patterns)
        except Exception as e:
            logger.error(f"API analysis failed: {e}")
            return None

    async def _run_testing_analysis(
        self, root_path: str, patterns: List[str]
    ) -> Optional[Dict[str, Any]]:
        """Run testing coverage analysis"""
        try:
            logger.info("Running testing coverage analysis...")
            return await self.testing_analyzer.analyze_testing_coverage(
                root_path, patterns
            )
        except Exception as e:
            logger.error(f"Testing analysis failed: {e}")
            return None

    async def _run_architecture_analysis(
        self, root_path: str, patterns: List[str]
    ) -> Optional[Dict[str, Any]]:
        """Run architectural pattern analysis"""
        try:
            logger.info("Running architectural pattern analysis...")
            return await self.architecture_analyzer.analyze_architecture(
                root_path, patterns
            )
        except Exception as e:
            logger.error(f"Architecture analysis failed: {e}")
            return None

    def _get_duplication_score(self, duplication_data: Optional[Dict]) -> float:
        """Calculate duplication score (Issue #340: extracted helper)."""
        if not duplication_data:
            return 100.0
        total_groups = duplication_data.get("total_duplicate_groups", 0)
        return max(0, 100 - (total_groups * 2))

    def _get_environment_score(self, env_data: Optional[Dict]) -> float:
        """Calculate environment config score (Issue #340: extracted helper)."""
        if not env_data:
            return 100.0
        critical_values = env_data.get("critical_hardcoded_values", 0)
        return max(0, 100 - (critical_values * 0.5))

    def _get_performance_score(self, perf_data: Optional[Dict]) -> float:
        """Calculate performance score (Issue #340: extracted helper)."""
        if not perf_data:
            return 100.0
        critical_issues = perf_data.get("critical_issues", 0)
        high_issues = perf_data.get("high_priority_issues", 0)
        return max(0, 100 - (critical_issues * 10 + high_issues * 5))

    def _get_security_score(self, security_data: Optional[Dict]) -> float:
        """Calculate security score (Issue #340: extracted helper)."""
        if not security_data or "metrics" not in security_data:
            return 100.0
        return security_data["metrics"].get("security_score", 50)

    def _get_api_score(self, api_data: Optional[Dict]) -> float:
        """Calculate API consistency score (Issue #340: extracted helper)."""
        if not api_data:
            return 100.0
        return api_data.get("consistency_score", 50)

    def _get_testing_score(self, testing_data: Optional[Dict]) -> float:
        """Calculate test coverage score (Issue #340: extracted helper)."""
        if not testing_data:
            return 0.0
        return testing_data.get("test_coverage_percentage", 0)

    def _get_architecture_score(self, arch_data: Optional[Dict]) -> float:
        """Calculate architecture score (Issue #340: extracted helper)."""
        if not arch_data:
            return 50.0
        return arch_data.get("architecture_score", 50)

    def _calculate_debt_factors(self, analysis_results: Dict[str, Any]) -> List[float]:
        """Calculate technical debt factors (Issue #340: extracted helper)."""
        debt_factors = []
        duplication = analysis_results.get("duplication")
        if duplication:
            debt_factors.append(
                min(50, duplication.get("total_duplicate_groups", 0) * 2)
            )
        security = analysis_results.get("security")
        if security:
            debt_factors.append(
                min(50, security.get("critical_vulnerabilities", 0) * 10)
            )
        performance = analysis_results.get("performance")
        if performance:
            debt_factors.append(min(50, performance.get("critical_issues", 0) * 5))
        return debt_factors

    def _calculate_quality_metrics(
        self, analysis_results: Dict[str, Any]
    ) -> QualityMetrics:
        """Calculate overall quality metrics (Issue #340: refactored)."""
        # Extract scores using helper methods
        duplication_score = self._get_duplication_score(
            analysis_results.get("duplication")
        )
        env_score = self._get_environment_score(analysis_results.get("environment"))
        performance_score = self._get_performance_score(
            analysis_results.get("performance")
        )
        security_score = self._get_security_score(analysis_results.get("security"))
        api_score = self._get_api_score(analysis_results.get("api_consistency"))
        test_coverage_score = self._get_testing_score(
            analysis_results.get("testing_coverage")
        )
        architecture_score = self._get_architecture_score(
            analysis_results.get("architecture")
        )

        # Calculate weighted overall score
        weights = {
            "security": 0.25,
            "performance": 0.20,
            "architecture": 0.15,
            "testing": 0.15,
            "api_consistency": 0.10,
            "duplication": 0.10,
            "environment": 0.05,
        }

        overall_score = (
            security_score * weights["security"]
            + performance_score * weights["performance"]
            + architecture_score * weights["architecture"]
            + test_coverage_score * weights["testing"]
            + api_score * weights["api_consistency"]
            + duplication_score * weights["duplication"]
            + env_score * weights["environment"]
        )

        maintainability = (
            architecture_score + test_coverage_score + duplication_score
        ) / 3

        debt_factors = self._calculate_debt_factors(analysis_results)
        technical_debt_ratio = (
            sum(debt_factors) / len(debt_factors) if debt_factors else 0
        )

        return QualityMetrics(
            overall_score=round(overall_score, 2),
            code_duplication_score=round(duplication_score, 2),
            environment_config_score=round(env_score, 2),
            performance_score=round(performance_score, 2),
            security_score=round(security_score, 2),
            api_consistency_score=round(api_score, 2),
            test_coverage_score=round(test_coverage_score, 2),
            architecture_score=round(architecture_score, 2),
            maintainability_index=round(maintainability, 2),
            technical_debt_ratio=round(technical_debt_ratio, 2),
        )

    def _extract_duplication_issues(
        self, duplication_data: Optional[Dict]
    ) -> List[QualityIssue]:
        """Extract issues from duplication analysis (Issue #340: extracted helper)."""
        if not duplication_data or "duplicate_groups" not in duplication_data:
            return []

        issues = []
        for group in duplication_data["duplicate_groups"][:10]:
            issues.append(
                QualityIssue(
                    category="code_duplication",
                    severity="medium",
                    title=f"Code duplication: {group.get('similarity', 0):.1f}% similar",
                    description=f"Found {group.get('count', 0)} duplicate code blocks",
                    file_path=group.get("files", [""])[0],
                    line_number=0,
                    fix_suggestion="Extract common code into shared utility functions",
                    estimated_effort="medium",
                    priority_score=60,
                )
            )
        return issues

    def _extract_environment_issues(
        self, env_data: Optional[Dict]
    ) -> List[QualityIssue]:
        """Extract issues from environment analysis (Issue #340: extracted helper)."""
        if not env_data or "critical_hardcoded_values" not in env_data:
            return []

        critical_categories = {"database_urls", "api_keys", "file_paths"}
        issues = []
        for value in env_data.get("hardcoded_values", [])[:20]:
            if value.get("category") not in critical_categories:
                continue
            issues.append(
                QualityIssue(
                    category="environment_configuration",
                    severity="high",
                    title=f"Hardcoded {value.get('category', 'value')}",
                    description=f"Found hardcoded {value.get('category')}: {value.get('value', '')[:50]}",
                    file_path=value.get("file", ""),
                    line_number=value.get("line", 0),
                    fix_suggestion="Move to environment variable or configuration file",
                    estimated_effort="low",
                    priority_score=70,
                )
            )
        return issues

    def _extract_security_issues(
        self, security_data: Optional[Dict]
    ) -> List[QualityIssue]:
        """Extract issues from security analysis (Issue #340: extracted helper)."""
        if not security_data or "vulnerability_details" not in security_data:
            return []

        priority_map = {"critical": 100, "high": 80, "medium": 60, "low": 40}
        issues = []
        for vuln in security_data["vulnerability_details"]:
            severity = vuln.get("severity", "low")
            issues.append(
                QualityIssue(
                    category="security",
                    severity=severity,
                    title=f"Security: {vuln.get('type', 'Unknown').replace('_', ' ').title()}",
                    description=vuln.get("description", ""),
                    file_path=vuln.get("file", ""),
                    line_number=vuln.get("line", 0),
                    fix_suggestion=vuln.get(
                        "fix_suggestion", "Review and fix security issue"
                    ),
                    estimated_effort="high" if severity == "critical" else "medium",
                    priority_score=priority_map.get(severity, 40),
                )
            )
        return issues

    def _extract_performance_issues(
        self, perf_data: Optional[Dict]
    ) -> List[QualityIssue]:
        """Extract issues from performance analysis (Issue #340: extracted helper)."""
        if not perf_data or "performance_details" not in perf_data:
            return []

        priority_map = {"critical": 90, "high": 70, "medium": 50, "low": 30}
        issues = []
        for perf in perf_data["performance_details"][:15]:
            severity = perf.get("severity", "low")
            issues.append(
                QualityIssue(
                    category="performance",
                    severity=severity,
                    title=f"Performance: {perf.get('type', 'Unknown').replace('_', ' ').title()}",
                    description=perf.get("description", ""),
                    file_path=perf.get("file", ""),
                    line_number=perf.get("line", 0),
                    fix_suggestion=perf.get(
                        "suggestion", "Optimize performance bottleneck"
                    ),
                    estimated_effort="medium",
                    priority_score=priority_map.get(severity, 30),
                )
            )
        return issues

    def _extract_api_issues(self, api_data: Optional[Dict]) -> List[QualityIssue]:
        """Extract issues from API consistency analysis (Issue #340: extracted helper)."""
        if not api_data or "inconsistencies" not in api_data:
            return []

        priority_map = {"high": 60, "medium": 40, "low": 20}
        issues = []
        for inconsistency in api_data["inconsistencies"]:
            severity = inconsistency.get("severity", "low")
            issues.append(
                QualityIssue(
                    category="api_consistency",
                    severity=severity,
                    title=f"API: {inconsistency.get('type', 'Unknown').replace('_', ' ').title()}",
                    description=inconsistency.get("description", ""),
                    file_path="Multiple files",
                    line_number=0,
                    fix_suggestion=inconsistency.get(
                        "suggestion", "Improve API consistency"
                    ),
                    estimated_effort="medium",
                    priority_score=priority_map.get(severity, 20),
                )
            )
        return issues

    def _extract_testing_issues(
        self, testing_data: Optional[Dict]
    ) -> List[QualityIssue]:
        """Extract issues from testing coverage analysis (Issue #340: extracted helper)."""
        if not testing_data or "coverage_gaps" not in testing_data:
            return []

        priority_map = {"critical": 85, "high": 65, "medium": 45, "low": 25}
        issues = []
        for gap in testing_data["coverage_gaps"]:
            severity = gap.get("severity", "medium")
            suggested_tests = gap.get("suggested_tests", [])[:2]
            issues.append(
                QualityIssue(
                    category="testing_coverage",
                    severity=severity,
                    title=f"Testing: {gap.get('type', 'Unknown').replace('_', ' ').title()}",
                    description=gap.get("description", ""),
                    file_path="Multiple files",
                    line_number=0,
                    fix_suggestion=f"Add missing tests: {', '.join(suggested_tests)}",
                    estimated_effort="medium",
                    priority_score=priority_map.get(severity, 45),
                )
            )
        return issues

    def _extract_architecture_issues(
        self, arch_data: Optional[Dict]
    ) -> List[QualityIssue]:
        """Extract issues from architectural analysis (Issue #340: extracted helper)."""
        if not arch_data or "architectural_issues" not in arch_data:
            return []

        priority_map = {"critical": 75, "high": 55, "medium": 35, "low": 15}
        issues = []
        for issue in arch_data["architectural_issues"]:
            severity = issue.get("severity", "medium")
            issues.append(
                QualityIssue(
                    category="architecture",
                    severity=severity,
                    title=f"Architecture: {issue.get('type', 'Unknown').replace('_', ' ').title()}",
                    description=issue.get("description", ""),
                    file_path="Multiple files",
                    line_number=0,
                    fix_suggestion=issue.get(
                        "suggestion", "Improve architectural design"
                    ),
                    estimated_effort=issue.get("refactoring_effort", "medium"),
                    priority_score=priority_map.get(severity, 35),
                )
            )
        return issues

    def _extract_all_issues(
        self, analysis_results: Dict[str, Any]
    ) -> List[QualityIssue]:
        """Extract all issues from analysis results (Issue #340: refactored)."""
        all_issues = []
        all_issues.extend(
            self._extract_duplication_issues(analysis_results.get("duplication"))
        )
        all_issues.extend(
            self._extract_environment_issues(analysis_results.get("environment"))
        )
        all_issues.extend(
            self._extract_security_issues(analysis_results.get("security"))
        )
        all_issues.extend(
            self._extract_performance_issues(analysis_results.get("performance"))
        )
        all_issues.extend(
            self._extract_api_issues(analysis_results.get("api_consistency"))
        )
        all_issues.extend(
            self._extract_testing_issues(analysis_results.get("testing_coverage"))
        )
        all_issues.extend(
            self._extract_architecture_issues(analysis_results.get("architecture"))
        )
        return all_issues

    def _prioritize_issues(self, issues: List[QualityIssue]) -> List[QualityIssue]:
        """Prioritize issues based on severity and impact"""

        # Sort by priority score (descending) and then by severity
        severity_weight = {"critical": 1000, "high": 100, "medium": 10, "low": 1}

        def priority_key(issue):
            return (
                severity_weight.get(issue.severity, 0) + issue.priority_score,
                issue.severity,
                issue.category,
            )

        return sorted(issues, key=priority_key, reverse=True)

    def _group_issues_by_category(self, issues: List[QualityIssue]) -> Dict[str, int]:
        """Group issues by category"""
        categories = {}
        for issue in issues:
            categories[issue.category] = categories.get(issue.category, 0) + 1
        return categories

    def _generate_improvement_recommendations(
        self, analysis_results: Dict[str, Any], issues: List[QualityIssue]
    ) -> List[str]:
        """Generate improvement recommendations based on analysis"""

        recommendations = []

        # Category-based recommendations
        categories = self._group_issues_by_category(issues)

        if categories.get("security", 0) > 0:
            recommendations.append(
                "🛡️ Address security vulnerabilities immediately - this is the highest priority"
            )

        if categories.get("performance", 0) > 5:
            recommendations.append(
                "⚡ Fix performance bottlenecks and memory leaks to improve system responsiveness"
            )

        if categories.get("testing_coverage", 0) > 0:
            recommendations.append(
                "🧪 Increase test coverage, especially for critical and complex functions"
            )

        if categories.get("architecture", 0) > 0:
            recommendations.append(
                "🏗️ Refactor architectural issues to improve maintainability and scalability"
            )

        if categories.get("code_duplication", 0) > 0:
            recommendations.append(
                "♻️ Eliminate code duplication by extracting common functionality"
            )

        if categories.get("api_consistency", 0) > 0:
            recommendations.append(
                "🔗 Standardize API patterns for better consistency and developer experience"
            )

        if categories.get("environment_configuration", 0) > 0:
            recommendations.append(
                "⚙️ Move hardcoded values to configuration files or environment variables"
            )

        # Quality score based recommendations
        if analysis_results.get("duplication"):
            total_groups = analysis_results["duplication"].get(
                "total_duplicate_groups", 0
            )
            if total_groups > 50:
                recommendations.append(
                    f"📊 High code duplication detected ({total_groups} groups) - consider major refactoring"
                )

        recommendations.extend(
            [
                "📈 Set up automated code quality monitoring in CI/CD pipeline",
                "📋 Implement pre-commit hooks for code quality checks",
                "🎯 Define and enforce coding standards across the team",
                "📚 Create technical debt backlog for systematic improvement",
            ]
        )
        return recommendations[:10]  # Top 10 recommendations

    def _calculate_technical_debt(self, issues: List[QualityIssue]) -> Dict[str, Any]:
        """Calculate technical debt metrics"""

        # Estimate effort in hours
        effort_mapping = {"low": 2, "medium": 8, "high": 24}

        total_effort = 0
        critical_effort = 0
        by_category = {}

        for issue in issues:
            effort = effort_mapping.get(issue.estimated_effort, 8)
            total_effort += effort

            if issue.severity == "critical":
                critical_effort += effort

            if issue.category not in by_category:
                by_category[issue.category] = {"count": 0, "effort_hours": 0}
            by_category[issue.category]["count"] += 1
            by_category[issue.category]["effort_hours"] += effort

        return {
            "total_issues": len(issues),
            "estimated_total_effort_hours": total_effort,
            "estimated_critical_effort_hours": critical_effort,
            "estimated_total_effort_days": round(total_effort / 8, 1),
            "effort_by_category": by_category,
            "debt_ratio": round(
                (total_effort / 1000) * 100, 2
            ),  # Percentage of total project effort
        }

    def _count_analyzed_files(self, analysis_results: Dict[str, Any]) -> int:
        """Count total files analyzed"""
        file_count = 0

        for analysis_type, results in analysis_results.items():
            if results and isinstance(results, dict):
                if "files_analyzed" in results:
                    file_count = max(file_count, results["files_analyzed"])
                elif "total_files" in results:
                    file_count = max(file_count, results["total_files"])

        return file_count

    def _serialize_issue(self, issue: QualityIssue) -> Dict[str, Any]:
        """Serialize issue for output"""
        return {
            "category": issue.category,
            "severity": issue.severity,
            "title": issue.title,
            "description": issue.description,
            "file_path": issue.file_path,
            "line_number": issue.line_number,
            "fix_suggestion": issue.fix_suggestion,
            "estimated_effort": issue.estimated_effort,
            "priority_score": issue.priority_score,
        }

    async def _save_quality_trend(self, metrics: QualityMetrics, issue_count: int):
        """Save quality trend data"""
        if self.redis_client:
            try:
                trend = QualityTrend(
                    timestamp=datetime.now(),
                    overall_score=metrics.overall_score,
                    issue_count=issue_count,
                    critical_issues=0,  # Would need to be calculated
                    files_analyzed=0,  # Would need to be calculated
                )

                trend_data = {
                    "timestamp": trend.timestamp.isoformat(),
                    "overall_score": trend.overall_score,
                    "issue_count": trend.issue_count,
                    "critical_issues": trend.critical_issues,
                    "files_analyzed": trend.files_analyzed,
                }

                # Store in Redis list (keep last 30 entries)
                await self.redis_client.lpush(self.TRENDS_KEY, json.dumps(trend_data))
                await self.redis_client.ltrim(self.TRENDS_KEY, 0, 29)
                await self.redis_client.expire(self.TRENDS_KEY, 86400 * 30)  # 30 days
            except Exception as e:
                logger.warning(f"Failed to save quality trend: {e}")

    async def _get_quality_trends(self) -> List[Dict[str, Any]]:
        """Get historical quality trends"""
        if self.redis_client:
            try:
                trends = await self.redis_client.lrange(self.TRENDS_KEY, 0, -1)
                return [json.loads(trend) for trend in trends]
            except Exception as e:
                logger.warning(f"Failed to get quality trends: {e}")
        return []

    async def _cache_dashboard_report(self, report: Dict[str, Any]):
        """Cache dashboard report"""
        if self.redis_client:
            try:
                await self.redis_client.setex(
                    self.DASHBOARD_KEY, 3600, json.dumps(report, default=str)  # 1 hour
                )
            except Exception as e:
                logger.warning(f"Failed to cache dashboard report: {e}")

    async def generate_executive_summary(self, report: Dict[str, Any]) -> str:
        """Generate executive summary from comprehensive report"""

        metrics = report["quality_metrics"]
        issues = report["issue_summary"]

        summary = f"""
# Code Quality Executive Summary

## Overall Assessment
- **Quality Score**: {metrics['overall_score']}/100
- **Total Issues**: {issues['total_issues']}
- **Critical Issues**: {issues['critical_issues']}
- **Analysis Date**: {report['timestamp']}

## Key Findings

### Security ({metrics['security_score']}/100)
{self._get_status_emoji(metrics['security_score'])} Security is {"GOOD" if metrics['security_score'] > 80 else "NEEDS ATTENTION"}

### Performance ({metrics['performance_score']}/100)
{self._get_status_emoji(metrics['performance_score'])} Performance is {"GOOD" if metrics['performance_score'] > 80 else "NEEDS ATTENTION"}

### Test Coverage ({metrics['test_coverage_score']}/100)
{self._get_status_emoji(metrics['test_coverage_score'])} Test coverage is {"GOOD" if metrics['test_coverage_score'] > 80 else "NEEDS IMPROVEMENT"}

### Architecture ({metrics['architecture_score']}/100)
{self._get_status_emoji(metrics['architecture_score'])} Architecture is {"GOOD" if metrics['architecture_score'] > 80 else "NEEDS IMPROVEMENT"}

## Technical Debt
- **Total Effort**: {report['technical_debt']['estimated_total_effort_days']} days
- **Critical Priority**: {report['technical_debt']['estimated_critical_effort_hours']} hours

## Immediate Actions Required
"""

        # Add top 3 recommendations
        for i, rec in enumerate(report["improvement_recommendations"][:3], 1):
            summary += f"{i}. {rec}\n"

        return summary

    def _get_status_emoji(self, score: float) -> str:
        """Get status emoji based on score"""
        if score >= 90:
            return "🟢"
        elif score >= 70:
            return "🟡"
        else:
            return "🔴"


async def main():
    """Example usage of code quality dashboard"""

    dashboard = CodeQualityDashboard()

    # Generate comprehensive report
    print("🚀 Generating comprehensive code quality report...")  # noqa: print
    report = await dashboard.generate_comprehensive_report(
        root_path=".", patterns=["src/**/*.py", "backend/**/*.py"], include_trends=True
    )

    # Print executive summary
    summary = await dashboard.generate_executive_summary(report)
    print(summary)  # noqa: print

    # Print detailed metrics
    metrics = report["quality_metrics"]
    print(f"\n=== Detailed Quality Metrics ===")  # noqa: print
    print(f"Overall Score: {metrics['overall_score']}/100")  # noqa: print
    print(f"Security: {metrics['security_score']}/100")  # noqa: print
    print(f"Performance: {metrics['performance_score']}/100")  # noqa: print
    print(f"Architecture: {metrics['architecture_score']}/100")  # noqa: print
    print(f"Test Coverage: {metrics['test_coverage_score']}/100")  # noqa: print
    print(f"API Consistency: {metrics['api_consistency_score']}/100")  # noqa: print
    print(f"Code Duplication: {metrics['code_duplication_score']}/100")  # noqa: print
    print(
        f"Environment Config: {metrics['environment_config_score']}/100"
    )  # noqa: print

    # Print top issues
    print(f"\n=== Top Priority Issues ===")  # noqa: print
    for i, issue in enumerate(report["prioritized_issues"][:10], 1):
        severity_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
        emoji = severity_emoji.get(issue["severity"], "⚪")
        print(f"{i}. {emoji} {issue['title']} ({issue['category']})")  # noqa: print
        print(f"   {issue['description']}")  # noqa: print
        print(f"   Fix: {issue['fix_suggestion']}")  # noqa: print
        print(f"   Effort: {issue['estimated_effort']}")  # noqa: print
        print()  # noqa: print

    # Save comprehensive report
    report_path = Path("comprehensive_quality_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"📋 Comprehensive report saved to: {report_path}")  # noqa: print

    return report


if __name__ == "__main__":
    asyncio.run(main())
