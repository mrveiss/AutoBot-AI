"""
Comprehensive Code Quality Dashboard

Integrates all analyzers: duplicates, environment variables, performance,
security, API consistency, testing coverage, and architectural patterns.
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
from config import config
from env_analyzer import EnvironmentVariableAnalyzer
from performance_analyzer import PerformanceAnalyzer
from security_analyzer import SecurityAnalyzer
from testing_coverage_analyzer import TestingCoverageAnalyzer
from utils.redis_client import get_redis_client

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

    async def _generate_comprehensive_report_block_3(self):
        """Run all analyses in parallel for better performance.

        Helper for generate_comprehensive_report (Issue #825).
        """
        # Run all analyses in parallel for better performance
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

    async def _generate_comprehensive_report_block_4(self):
        """Process results.

        Helper for generate_comprehensive_report (Issue #825).
        """
        # Process results
        (
            duplication_results,
            env_results,
            performance_results,
            security_results,
            api_results,
            testing_results,
            architecture_results,
        ) = analyses

    async def _generate_comprehensive_report_block_2(self):
        """Handle any analysis failures.

        Helper for generate_comprehensive_report (Issue #825).
        """
        # Handle any analysis failures
        analysis_results = {
            "duplication": duplication_results
            if not isinstance(duplication_results, Exception)
            else None,
            "environment": env_results
            if not isinstance(env_results, Exception)
            else None,
            "performance": performance_results
            if not isinstance(performance_results, Exception)
            else None,
            "security": security_results
            if not isinstance(security_results, Exception)
            else None,
            "api_consistency": api_results
            if not isinstance(api_results, Exception)
            else None,
            "testing_coverage": testing_results
            if not isinstance(testing_results, Exception)
            else None,
            "architecture": architecture_results
            if not isinstance(architecture_results, Exception)
            else None,
        }

    async def _generate_comprehensive_report_block_1(self):
        """comprehensive_report = {.

        Helper for generate_comprehensive_report (Issue #825).
        """
        comprehensive_report = {
            "timestamp": datetime.now().isoformat(),
            "analysis_time_seconds": analysis_time,
            "overall_quality_score": quality_metrics.overall_score,
            "quality_metrics": {
                "overall_score": quality_metrics.overall_score,
                "code_duplication_score": quality_metrics.code_duplication_score,
                "environment_config_score": quality_metrics.environment_config_score,
                "performance_score": quality_metrics.performance_score,
                "security_score": quality_metrics.security_score,
                "api_consistency_score": quality_metrics.api_consistency_score,
                "test_coverage_score": quality_metrics.test_coverage_score,
                "architecture_score": quality_metrics.architecture_score,
                "maintainability_index": quality_metrics.maintainability_index,
                "technical_debt_ratio": quality_metrics.technical_debt_ratio,
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
                self._serialize_issue(issue) for issue in prioritized_issues[:50]
            ],  # Top 50 issues
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

        await self._generate_comprehensive_report_block_3()

        await self._generate_comprehensive_report_block_4()

        await self._generate_comprehensive_report_block_2()

        # Calculate overall quality metrics
        quality_metrics = self._calculate_quality_metrics(analysis_results)

        # Extract and prioritize issues
        all_issues = self._extract_all_issues(analysis_results)
        prioritized_issues = self._prioritize_issues(all_issues)

        # Generate improvement recommendations
        recommendations = self._generate_improvement_recommendations(
            analysis_results, prioritized_issues
        )

        # Calculate technical debt
        self._calculate_technical_debt(prioritized_issues)

        analysis_time = time.time() - start_time

        # Generate trend data if requested
        if include_trends:
            await self._get_quality_trends()

        await self._generate_comprehensive_report_block_1()

        # Save current analysis for trend tracking
        await self._save_quality_trend(quality_metrics, len(all_issues))

        # Cache comprehensive report
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

    def __calculate_quality_metrics_block_5(self):
        """Extract scores from each analysis (default to 50 if analysis.

        Helper for _calculate_quality_metrics (Issue #825).
        """

        # Extract scores from each analysis (default to 50 if analysis failed)
        duplication_score = 100  # Start high, reduce based on duplicates found
        if analysis_results.get("duplication"):
            total_groups = analysis_results["duplication"].get(
                "total_duplicate_groups", 0
            )
            max(0, 100 - (total_groups * 2))

    def __calculate_quality_metrics_block_7(self):
        """env_score = 100  # Start high, reduce based on hardcoded val.

        Helper for _calculate_quality_metrics (Issue #825).
        """
        env_score = 100  # Start high, reduce based on hardcoded values
        if analysis_results.get("environment"):
            critical_values = analysis_results["environment"].get(
                "critical_hardcoded_values", 0
            )
            max(0, 100 - (critical_values * 0.5))

    def __calculate_quality_metrics_block_6(self):
        """security_score = 100.

        Helper for _calculate_quality_metrics (Issue #825).
        """
        security_score = 100
        if (
            analysis_results.get("security")
            and "metrics" in analysis_results["security"]
        ):
            security_score = analysis_results["security"]["metrics"].get(
                "security_score", 50
            )

    def __calculate_quality_metrics_block_3(self):
        """Calculate weighted overall score.

        Helper for _calculate_quality_metrics (Issue #825).
        """
        # Calculate weighted overall score
        weights = {
            "security": 0.25,  # Security is most important
            "performance": 0.20,  # Performance is critical
            "architecture": 0.15,  # Good architecture is key to maintainability
            "testing": 0.15,  # Testing coverage is important
            "api_consistency": 0.10,
            "duplication": 0.10,
            "environment": 0.05,
        }

    def __calculate_quality_metrics_block_4(self):
        """overall_score = (.

        Helper for _calculate_quality_metrics (Issue #825).
        """
        overall_score = (
            security_score * weights["security"]
            + performance_score * weights["performance"]
            + architecture_score * weights["architecture"]
            + test_coverage_score * weights["testing"]
            + api_score * weights["api_consistency"]
            + duplication_score * weights["duplication"]
            + env_score * weights["environment"]
        )

    def __calculate_quality_metrics_block_1(self):
        """Calculate technical debt ratio (higher is worse).

        Helper for _calculate_quality_metrics (Issue #825).
        """
        # Calculate technical debt ratio (higher is worse)
        debt_factors = []
        if analysis_results.get("duplication"):
            debt_factors.append(
                min(
                    50,
                    analysis_results["duplication"].get("total_duplicate_groups", 0)
                    * 2,
                )
            )
        if analysis_results.get("security"):
            critical_vulns = analysis_results["security"].get(
                "critical_vulnerabilities", 0
            )
            debt_factors.append(min(50, critical_vulns * 10))
        if analysis_results.get("performance"):
            critical_perf = analysis_results["performance"].get("critical_issues", 0)
            debt_factors.append(min(50, critical_perf * 5))

    def __calculate_quality_metrics_block_2(self):
        """return QualityMetrics(.

        Helper for _calculate_quality_metrics (Issue #825).
        """
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

    def _calculate_quality_metrics(
        self, analysis_results: Dict[str, Any]
    ) -> QualityMetrics:
        """Calculate overall quality metrics"""
        self.__calculate_quality_metrics_block_5()

        self.__calculate_quality_metrics_block_7()

        performance_score = 100  # Start high, reduce based on issues
        if analysis_results.get("performance"):
            critical_issues = analysis_results["performance"].get("critical_issues", 0)
            high_issues = analysis_results["performance"].get("high_priority_issues", 0)
            max(0, 100 - (critical_issues * 10 + high_issues * 5))

        self.__calculate_quality_metrics_block_6()

        if analysis_results.get("api_consistency"):
            analysis_results["api_consistency"].get("consistency_score", 50)

        test_coverage_score = 0
        if analysis_results.get("testing_coverage"):
            test_coverage_score = analysis_results["testing_coverage"].get(
                "test_coverage_percentage", 0
            )

        architecture_score = 50
        if analysis_results.get("architecture"):
            architecture_score = analysis_results["architecture"].get(
                "architecture_score", 50
            )

        self.__calculate_quality_metrics_block_3()

        self.__calculate_quality_metrics_block_4()

        # Calculate maintainability index (simplified)
        maintainability = (
            architecture_score + test_coverage_score + duplication_score
        ) / 3

        self.__calculate_quality_metrics_block_1()

        technical_debt_ratio = (
            sum(debt_factors) / len(debt_factors) if debt_factors else 0
        )

        self.__calculate_quality_metrics_block_2()

    def __extract_all_issues_block_2(self):
        """Extract duplication issues.

        Helper for _extract_all_issues (Issue #825).
        """
        # Extract duplication issues
        if (
            analysis_results.get("duplication")
            and "duplicate_groups" in analysis_results["duplication"]
        ):
            for group in analysis_results["duplication"]["duplicate_groups"][
                :10
            ]:  # Top 10 duplicate groups
                all_issues.append(
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

    def __extract_all_issues_block_1(self):
        """Extract environment issues.

        Helper for _extract_all_issues (Issue #825).
        """
        # Extract environment issues
        if (
            analysis_results.get("environment")
            and "critical_hardcoded_values" in analysis_results["environment"]
        ):
            for value in analysis_results["environment"].get("hardcoded_values", [])[
                :20
            ]:  # Top 20
                if value.get("category") in ["database_urls", "api_keys", "file_paths"]:
                    all_issues.append(
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

    def __extract_all_issues_block_9(self):
        """Extract security issues.

        Helper for _extract_all_issues (Issue #825).
        """
        # Extract security issues
        if (
            analysis_results.get("security")
            and "vulnerability_details" in analysis_results["security"]
        ):
            for vuln in analysis_results["security"]["vulnerability_details"]:
                severity = vuln.get("severity", "low")
                priority = {"critical": 100, "high": 80, "medium": 60, "low": 40}.get(
                    severity, 40
                )

    def __extract_all_issues_block_3(self):
        """all_issues.append(.

        Helper for _extract_all_issues (Issue #825).
        """
        all_issues.append(
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
                priority_score=priority,
            )
        )

    def __extract_all_issues_block_8(self):
        """Extract performance issues.

        Helper for _extract_all_issues (Issue #825).
        """
        # Extract performance issues
        if (
            analysis_results.get("performance")
            and "performance_details" in analysis_results["performance"]
        ):
            for perf in analysis_results["performance"]["performance_details"][
                :15
            ]:  # Top 15
                severity = perf.get("severity", "low")
                priority = {"critical": 90, "high": 70, "medium": 50, "low": 30}.get(
                    severity, 30
                )

    def __extract_all_issues_block_4(self):
        """all_issues.append(.

        Helper for _extract_all_issues (Issue #825).
        """
        all_issues.append(
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
                priority_score=priority,
            )
        )

    def __extract_all_issues_block_5(self):
        """all_issues.append(.

        Helper for _extract_all_issues (Issue #825).
        """
        all_issues.append(
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
                priority_score=priority,
            )
        )

    def __extract_all_issues_block_10(self):
        """Extract testing issues.

        Helper for _extract_all_issues (Issue #825).
        """
        # Extract testing issues
        if (
            analysis_results.get("testing_coverage")
            and "coverage_gaps" in analysis_results["testing_coverage"]
        ):
            for gap in analysis_results["testing_coverage"]["coverage_gaps"]:
                severity = gap.get("severity", "medium")
                priority = {"critical": 85, "high": 65, "medium": 45, "low": 25}.get(
                    severity, 45
                )

    def __extract_all_issues_block_7(self):
        """all_issues.append(.

        Helper for _extract_all_issues (Issue #825).
        """
        all_issues.append(
            QualityIssue(
                category="testing_coverage",
                severity=severity,
                title=f"Testing: {gap.get('type', 'Unknown').replace('_', ' ').title()}",
                description=gap.get("description", ""),
                file_path="Multiple files",
                line_number=0,
                fix_suggestion=f"Add missing tests: {', '.join(gap.get('suggested_tests', [])[:2])}",
                estimated_effort="medium",
                priority_score=priority,
            )
        )

    def __extract_all_issues_block_6(self):
        """all_issues.append(.

        Helper for _extract_all_issues (Issue #825).
        """
        all_issues.append(
            QualityIssue(
                category="architecture",
                severity=severity,
                title=f"Architecture: {issue.get('type', 'Unknown').replace('_', ' ').title()}",
                description=issue.get("description", ""),
                file_path="Multiple files",
                line_number=0,
                fix_suggestion=issue.get("suggestion", "Improve architectural design"),
                estimated_effort=issue.get("refactoring_effort", "medium"),
                priority_score=priority,
            )
        )

    def _extract_all_issues(
        self, analysis_results: Dict[str, Any]
    ) -> List[QualityIssue]:
        """Extract all issues from analysis results"""

        all_issues = []

        self.__extract_all_issues_block_2()

        self.__extract_all_issues_block_1()

        self.__extract_all_issues_block_9()

        self.__extract_all_issues_block_3()

        self.__extract_all_issues_block_8()

        self.__extract_all_issues_block_4()

        # Extract API consistency issues
        if (
            analysis_results.get("api_consistency")
            and "inconsistencies" in analysis_results["api_consistency"]
        ):
            for inconsistency in analysis_results["api_consistency"]["inconsistencies"]:
                severity = inconsistency.get("severity", "low")
                priority = {"high": 60, "medium": 40, "low": 20}.get(severity, 20)

        self.__extract_all_issues_block_5()

        self.__extract_all_issues_block_10()

        self.__extract_all_issues_block_7()

        # Extract architectural issues
        if (
            analysis_results.get("architecture")
            and "architectural_issues" in analysis_results["architecture"]
        ):
            for issue in analysis_results["architecture"]["architectural_issues"]:
                severity = issue.get("severity", "medium")
                priority = {"critical": 75, "high": 55, "medium": 35, "low": 15}.get(
                    severity, 35
                )

        self.__extract_all_issues_block_6()

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

    def __generate_improvement_recommendations_block_1(self):
        """Quality score based recommendations.

        Helper for _generate_improvement_recommendations (Issue #825).
        """
        # Quality score based recommendations
        if analysis_results.get("duplication"):
            total_groups = analysis_results["duplication"].get(
                "total_duplicate_groups", 0
            )
            if total_groups > 50:
                recommendations.append(
                    f"📊 High code duplication detected ({total_groups} groups) - consider major refactoring"
                )

    def __generate_improvement_recommendations_block_2(self):
        """Add general best practices.

        Helper for _generate_improvement_recommendations (Issue #825).
        """
        # Add general best practices
        recommendations.extend(
            [
                "📈 Set up automated code quality monitoring in CI/CD pipeline",
                "📋 Implement pre-commit hooks for code quality checks",
                "🎯 Define and enforce coding standards across the team",
                "📚 Create technical debt backlog for systematic improvement",
            ]
        )

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

        self.__generate_improvement_recommendations_block_1()

        self.__generate_improvement_recommendations_block_2()

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

        # Pre-compute status strings to avoid long lines
        sec_status = "GOOD" if metrics["security_score"] > 80 else "NEEDS ATTENTION"
        perf_status = "GOOD" if metrics["performance_score"] > 80 else "NEEDS ATTENTION"
        test_status = (
            "GOOD" if metrics["test_coverage_score"] > 80 else "NEEDS IMPROVEMENT"
        )
        arch_status = (
            "GOOD" if metrics["architecture_score"] > 80 else "NEEDS IMPROVEMENT"
        )

        sec_emoji = self._get_status_emoji(metrics["security_score"])
        perf_emoji = self._get_status_emoji(metrics["performance_score"])
        test_emoji = self._get_status_emoji(metrics["test_coverage_score"])
        arch_emoji = self._get_status_emoji(metrics["architecture_score"])

        summary = f"""
# Code Quality Executive Summary

## Overall Assessment
- **Quality Score**: {metrics['overall_score']}/100
- **Total Issues**: {issues['total_issues']}
- **Critical Issues**: {issues['critical_issues']}
- **Analysis Date**: {report['timestamp']}

## Key Findings

### Security ({metrics['security_score']}/100)
{sec_emoji} Security is {sec_status}

### Performance ({metrics['performance_score']}/100)
{perf_emoji} Performance is {perf_status}

### Test Coverage ({metrics['test_coverage_score']}/100)
{test_emoji} Test coverage is {test_status}

### Architecture ({metrics['architecture_score']}/100)
{arch_emoji} Architecture is {arch_status}

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
    logger.info("🚀 Generating comprehensive code quality report...")
    report = await dashboard.generate_comprehensive_report(
        root_path=".", patterns=["src/**/*.py", "backend/**/*.py"], include_trends=True
    )

    # Print executive summary
    summary = await dashboard.generate_executive_summary(report)
    logger.info(summary)

    # Print detailed metrics
    metrics = report["quality_metrics"]
    logger.info(f"\n=== Detailed Quality Metrics ===")
    logger.info(f"Overall Score: {metrics['overall_score']}/100")
    logger.info(f"Security: {metrics['security_score']}/100")
    logger.info(f"Performance: {metrics['performance_score']}/100")
    logger.info(f"Architecture: {metrics['architecture_score']}/100")
    logger.info(f"Test Coverage: {metrics['test_coverage_score']}/100")
    logger.info(f"API Consistency: {metrics['api_consistency_score']}/100")
    logger.info(f"Code Duplication: {metrics['code_duplication_score']}/100")
    logger.info(f"Environment Config: {metrics['environment_config_score']}/100")

    # Print top issues
    logger.info(f"\n=== Top Priority Issues ===")
    for i, issue in enumerate(report["prioritized_issues"][:10], 1):
        severity_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
        emoji = severity_emoji.get(issue["severity"], "⚪")
        logger.info(f"{i}. {emoji} {issue['title']} ({issue['category']})")
        logger.info(f"   {issue['description']}")
        logger.info(f"   Fix: {issue['fix_suggestion']}")
        logger.info(f"   Effort: {issue['estimated_effort']}")
        logger.info("")

    # Save comprehensive report
    report_path = Path("comprehensive_quality_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    logger.info(f"📋 Comprehensive report saved to: {report_path}")

    return report


if __name__ == "__main__":
    asyncio.run(main())
