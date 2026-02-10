#!/usr/bin/env python3
"""
Comprehensive Code Quality Analysis Dashboard
Runs all analyzers and provides unified quality metrics and recommendations
"""

import asyncio
import json
from pathlib import Path

import logging

from src.code_quality_dashboard import CodeQualityDashboard

logger = logging.getLogger(__name__)


async def _display_overall_metrics(report):
    """Display overall quality assessment metrics.

    Helper for run_comprehensive_quality_analysis (Issue #825).
    """
    metrics = report["quality_metrics"]
    issues = report["issue_summary"]

    logger.info(f"📊 **Overall Quality Assessment:**")
    logger.info(f"   🎯 Overall Quality Score: {metrics['overall_score']}/100")
    logger.info(f"   📋 Total Issues Found: {issues['total_issues']}")
    logger.error(f"   🚨 Critical Issues: {issues['critical_issues']}")
    logger.warning(f"   ⚠️  High Priority Issues: {issues['high_priority_issues']}")
    logger.info(f"   📁 Files Analyzed: {report['files_analyzed']}")
    logger.info(f"   ⏱️  Analysis Time: {report['analysis_time_seconds']:.2f} seconds")
    logger.info("")

    # Category breakdown
    logger.info("🏷️  **Issues by Category:**")
    for category, count in issues["by_category"].items():
        category_name = category.replace("_", " ").title()
        logger.info(f"   • {category_name}: {count} issues")
    logger.info("")


async def _display_analyzer_scores(metrics):
    """Display individual analyzer scores.

    Helper for run_comprehensive_quality_analysis (Issue #825).
    """
    logger.info("🔍 **Individual Analysis Scores:**")
    score_categories = [
        ("Security", metrics["security_score"], "🛡️"),
        ("Performance", metrics["performance_score"], "⚡"),
        ("Architecture", metrics["architecture_score"], "🏗️"),
        ("Test Coverage", metrics["test_coverage_score"], "🧪"),
        ("API Consistency", metrics["api_consistency_score"], "🔗"),
        ("Code Duplication", metrics["code_duplication_score"], "♻️"),
        ("Environment Config", metrics["environment_config_score"], "⚙️"),
    ]

    for name, score, emoji in score_categories:
        status = get_score_status(score)
        status_color = get_status_emoji(score)
        logger.info(f"   {emoji} {name}: {score}/100 {status_color} {status}")
    logger.info("")


async def _display_technical_debt(debt):
    """Display technical debt analysis.

    Helper for run_comprehensive_quality_analysis (Issue #825).
    """
    logger.info("💸 **Technical Debt Analysis:**")
    logger.info(
        "   📊 Total Estimated Effort: %s days (%s hours)",
        debt['estimated_total_effort_days'],
        debt['estimated_total_effort_hours'],
    )
    logger.info("   🚨 Critical Issues Effort: %s hours", debt['estimated_critical_effort_hours'])
    logger.info(f"   📈 Debt Ratio: {debt['debt_ratio']}% of total project")
    logger.info("")

    logger.info("💰 **Effort by Category:**")
    for category, data in debt["effort_by_category"].items():
        category_name = category.replace("_", " ").title()
        logger.info("   • %s: %s issues, %s hours", category_name, data['count'], data['effort_hours'])
    logger.info("")


async def _display_top_priority_issues(report):
    """Display top priority issues.

    Helper for run_comprehensive_quality_analysis (Issue #825).
    """
    logger.info("🚨 **Top Priority Issues (Immediate Action Required):**")
    critical_issues = [
        issue
        for issue in report["prioritized_issues"]
        if issue["severity"] == "critical"
    ]
    high_issues = [
        issue for issue in report["prioritized_issues"] if issue["severity"] == "high"
    ]

    top_issues = critical_issues[:5] + high_issues[:5]

    for i, issue in enumerate(top_issues[:10], 1):
        severity_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
        emoji = severity_emoji.get(issue["severity"], "⚪")

        logger.info(f"\n{i}. {emoji} **{issue['title']}** ({issue['severity'].upper()})")
        logger.info(f"   📂 Category: {issue['category'].replace('_', ' ').title()}")
        if issue["file_path"] != "Multiple files":
            logger.info(f"   📄 File: {issue['file_path']}:{issue['line_number']}")
        logger.info(f"   📝 Description: {issue['description']}")
        logger.info(f"   💡 Fix: {issue['fix_suggestion']}")
        logger.info(f"   🔧 Effort: {issue['estimated_effort'].title()}")
        logger.info(f"   🎯 Priority Score: {issue['priority_score']}/100")

    logger.info("")


async def _display_critical_alerts(report):
    """Display critical security and performance alerts.

    Helper for run_comprehensive_quality_analysis (Issue #825).
    """
    # Security-specific analysis
    if report["detailed_analyses"].get("security"):
        security_data = report["detailed_analyses"]["security"]
        if security_data.get("critical_vulnerabilities", 0) > 0:
            logger.error("🛡️ **CRITICAL SECURITY ALERT:**")
            logger.info("   Found %s critical security vulnerabilities!", security_data['critical_vulnerabilities'])
            logger.info("   These must be addressed immediately before deployment.")
            logger.info("")

    # Performance-specific analysis
    if report["detailed_analyses"].get("performance"):
        perf_data = report["detailed_analyses"]["performance"]
        if perf_data.get("critical_issues", 0) > 0:
            logger.error("⚡ **CRITICAL PERFORMANCE ALERT:**")
            logger.info("   Found %s critical performance issues!", perf_data['critical_issues'])
            logger.info("   These may cause memory leaks or system instability.")
            logger.info("")

    # Testing coverage analysis
    if report["detailed_analyses"].get("testing_coverage"):
        test_data = report["detailed_analyses"]["testing_coverage"]
        coverage = test_data.get("test_coverage_percentage", 0)
        logger.info(f"🧪 **Testing Coverage Analysis:**")
        logger.info(f"   Current test coverage: {coverage}%")
        if coverage < 70:
            logger.warning("   ⚠️  Coverage is below recommended 70% threshold")
            logger.info("   Consider adding more unit and integration tests")
        logger.info("")


async def _display_recommendations_and_trends(report):
    """Display improvement recommendations and quality trends.

    Helper for run_comprehensive_quality_analysis (Issue #825).
    """
    # Improvement recommendations
    logger.info("📋 **Improvement Recommendations (Priority Order):**")
    for i, recommendation in enumerate(report["improvement_recommendations"], 1):
        logger.info(f"{i}. {recommendation}")
    logger.info("")

    # Quality trends (if available)
    if report.get("quality_trends"):
        logger.info("📈 **Quality Trends:**")
        trends = report["quality_trends"]
        if len(trends) > 1:
            latest = trends[0]
            previous = trends[1]
            score_change = latest["overall_score"] - previous["overall_score"]
            trend_emoji = "📈" if score_change > 0 else "📉" if score_change < 0 else "➡️"
            logger.info(f"   {trend_emoji} Score change: {score_change:+.1f} points")

            issue_change = latest["issue_count"] - previous["issue_count"]
            issue_emoji = "📉" if issue_change < 0 else "📈" if issue_change > 0 else "➡️"
            logger.info(f"   {issue_emoji} Issue count change: {issue_change:+d}")
        else:
            logger.info("   📊 Baseline measurement established")
        logger.info("")


async def _display_detailed_analysis_summaries(report):
    """Display detailed analysis summaries for each analyzer.

    Helper for run_comprehensive_quality_analysis (Issue #825).
    """
    logger.info("📊 **Detailed Analysis Summaries:**")

    analysis_summaries = {
        "duplication": ("Code Duplication", "♻️"),
        "environment": ("Environment Variables", "⚙️"),
        "performance": ("Performance", "⚡"),
        "security": ("Security", "🛡️"),
        "api_consistency": ("API Consistency", "🔗"),
        "testing_coverage": ("Testing Coverage", "🧪"),
        "architecture": ("Architecture", "🏗️"),
    }

    for analysis_type, (name, emoji) in analysis_summaries.items():
        data = report["detailed_analyses"].get(analysis_type)
        if data:
            logger.info(f"\n{emoji} **{name} Analysis:**")

            if analysis_type == "duplication":
                groups = data.get("total_duplicate_groups", 0)
                lines_saved = data.get("total_lines_saved", 0)
                logger.info(f"   • Found {groups} duplicate code groups")
                logger.info(f"   • Potential lines saved: {lines_saved}")

            elif analysis_type == "environment":
                critical = data.get("critical_hardcoded_values", 0)
                total = data.get("total_hardcoded_values", 0)
                logger.info(f"   • Found {total} hardcoded values")
                logger.error(f"   • Critical values: {critical}")

            elif analysis_type == "security":
                vulns = data.get("total_vulnerabilities", 0)
                critical_vulns = data.get("critical_vulnerabilities", 0)
                logger.info(f"   • Found {vulns} potential vulnerabilities")
                logger.error(f"   • Critical vulnerabilities: {critical_vulns}")

            elif analysis_type == "performance":
                total_issues = data.get("total_performance_issues", 0)
                critical_issues = data.get("critical_issues", 0)
                logger.info(f"   • Found {total_issues} performance issues")
                logger.error(f"   • Critical issues: {critical_issues}")

            elif analysis_type == "api_consistency":
                endpoints = data.get("total_endpoints", 0)
                inconsistencies = data.get("inconsistencies_found", 0)
                logger.info(f"   • Analyzed {endpoints} API endpoints")
                logger.info(f"   • Found {inconsistencies} consistency issues")

            elif analysis_type == "testing_coverage":
                total_funcs = data.get("total_functions", 0)
                coverage = data.get("test_coverage_percentage", 0)
                logger.info(f"   • Analyzed {total_funcs} functions")
                logger.info(f"   • Test coverage: {coverage}%")

            elif analysis_type == "architecture":
                components = data.get("total_components", 0)
                arch_issues = data.get("architectural_issues", 0)
                logger.info(f"   • Analyzed {components} architectural components")
                logger.info(f"   • Found {arch_issues} architectural issues")


async def run_comprehensive_quality_analysis():
    """Run comprehensive code quality analysis"""

    logger.info("🎯 Starting comprehensive code quality analysis...")
    logger.info("This will run all available analyzers:")
    logger.info("  • Code Duplication Analyzer")
    logger.info("  • Environment Variable Analyzer")
    logger.info("  • Performance & Memory Leak Analyzer")
    logger.info("  • Security Vulnerability Analyzer")
    logger.info("  • API Consistency Analyzer")
    logger.info("  • Testing Coverage Gap Analyzer")
    logger.info("  • Architectural Pattern Analyzer")
    logger.info("")

    dashboard = CodeQualityDashboard()

    # Generate comprehensive report
    report = await dashboard.generate_comprehensive_report(
        root_path=".", patterns=["src/**/*.py", "backend/**/*.py"], include_trends=True
    )

    logger.info("=== Code Quality Executive Summary ===\n")

    # Executive summary
    summary = await dashboard.generate_executive_summary(report)
    logger.info(summary)

    logger.info("\n=== Detailed Quality Analysis Results ===\n")

    await _display_overall_metrics(report)
    await _display_analyzer_scores(report["quality_metrics"])
    await _display_technical_debt(report["technical_debt"])
    await _display_top_priority_issues(report)
    await _display_critical_alerts(report)
    await _display_recommendations_and_trends(report)
    await _display_detailed_analysis_summaries(report)

    # Save comprehensive report
    report_path = Path("comprehensive_quality_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    # Generate summary report
    summary_path = Path("quality_summary.txt")
    with open(summary_path, "w") as f:
        f.write(summary)

    logger.info(f"\n=== Reports Generated ===")
    logger.info(f"📋 Comprehensive report: {report_path}")
    logger.info(f"📄 Executive summary: {summary_path}")

    return report


def get_score_status(score: float) -> str:
    """Get human-readable status for score"""
    if score >= 90:
        return "EXCELLENT"
    elif score >= 80:
        return "GOOD"
    elif score >= 70:
        return "FAIR"
    elif score >= 60:
        return "NEEDS IMPROVEMENT"
    else:
        return "CRITICAL"


def get_status_emoji(score: float) -> str:
    """Get status emoji based on score"""
    if score >= 90:
        return "🟢"
    elif score >= 80:
        return "🟡"
    elif score >= 70:
        return "🟠"
    else:
        return "🔴"


async def generate_action_plan(report):
    """Generate specific action plan based on results"""

    logger.info("\n=== 📋 Recommended Action Plan ===")

    metrics = report["quality_metrics"]
    issues = report["issue_summary"]

    # Phase 1: Critical Issues (Week 1)
    critical_count = issues["critical_issues"]
    if critical_count > 0:
        logger.error(f"\n🚨 **Phase 1: Critical Issues (IMMEDIATE - Week 1)**")
        logger.error(f"   Address {critical_count} critical issues:")

        critical_issues = [
            i for i in report["prioritized_issues"] if i["severity"] == "critical"
        ]
        for issue in critical_issues[:5]:  # Top 5 critical
            logger.info(f"   • {issue['title']}")
            logger.info(f"     Action: {issue['fix_suggestion']}")

    # Phase 2: High Priority (Weeks 2-3)
    high_count = issues["high_priority_issues"]
    if high_count > 0:
        logger.warning(f"\n⚠️  **Phase 2: High Priority (Weeks 2-3)**")
        logger.info(f"   Address {high_count} high priority issues:")

        if metrics["security_score"] < 80:
            logger.info("   • Complete security vulnerability audit")
        if metrics["performance_score"] < 70:
            logger.info("   • Fix performance bottlenecks and memory leaks")
        if metrics["test_coverage_score"] < 70:
            logger.info("   • Increase test coverage to 80%+")

    # Phase 3: Quality Improvements (Month 2)
    logger.info(f"\n🔧 **Phase 3: Quality Improvements (Month 2)**")
    if metrics["architecture_score"] < 80:
        logger.info("   • Refactor architectural issues")
    if metrics["code_duplication_score"] < 80:
        logger.info("   • Eliminate code duplication")
    if metrics["api_consistency_score"] < 80:
        logger.info("   • Standardize API patterns")

    # Phase 4: Maintenance & Monitoring (Ongoing)
    logger.info(f"\n📈 **Phase 4: Continuous Improvement (Ongoing)**")
    logger.info("   • Set up automated quality monitoring")
    logger.info("   • Implement pre-commit quality checks")
    logger.info("   • Regular quality reviews (weekly)")
    logger.info("   • Update team coding standards")

    # Estimated timeline
    debt = report["technical_debt"]
    total_days = debt["estimated_total_effort_days"]
    critical_hours = debt["estimated_critical_effort_hours"]

    logger.info(f"\n⏰ **Estimated Timeline:**")
    logger.error(f"   • Critical fixes: {critical_hours} hours (1-2 weeks)")
    logger.info(f"   • Total remediation: {total_days} days ({total_days/5:.1f} weeks)")
    logger.info(f"   • Team of 2-3 developers recommended")


async def main():
    """Run comprehensive code quality analysis"""

    # Run analysis
    report = await run_comprehensive_quality_analysis()

    # Generate action plan
    await generate_action_plan(report)

    logger.info("\n=== 🎯 Analysis Complete ===")
    logger.info("Next Steps:")
    logger.info("1. Review comprehensive_quality_report.json for detailed findings")
    logger.error("2. Start with critical security and performance issues")
    logger.info("3. Follow the recommended action plan phases")
    logger.info("4. Set up automated quality monitoring")
    logger.info("5. Schedule regular quality reviews")


if __name__ == "__main__":
    asyncio.run(main())
