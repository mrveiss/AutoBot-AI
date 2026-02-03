#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Comprehensive Code Quality Analysis Dashboard
Runs all analyzers and provides unified quality metrics and recommendations

NOTE: run_comprehensive_quality_analysis (~145 lines) is an ACCEPTABLE EXCEPTION
per Issue #490 - analysis dashboard with sequential report generation. Low priority.
"""

import asyncio
import json
from pathlib import Path

from src.code_quality_dashboard import CodeQualityDashboard


def _print_executive_metrics(metrics: dict, issues: dict, report: dict) -> None:
    """
    Print executive-level quality metrics summary.

    Issue #281: Extracted from run_comprehensive_quality_analysis to reduce
    function length and improve readability of dashboard output sections.
    """
    print(f"📊 **Overall Quality Assessment:**")
    print(f"   🎯 Overall Quality Score: {metrics['overall_score']}/100")
    print(f"   📋 Total Issues Found: {issues['total_issues']}")
    print(f"   🚨 Critical Issues: {issues['critical_issues']}")
    print(f"   ⚠️  High Priority Issues: {issues['high_priority_issues']}")
    print(f"   📁 Files Analyzed: {report['files_analyzed']}")
    print(f"   ⏱️  Analysis Time: {report['analysis_time_seconds']:.2f} seconds")
    print()

    # Category breakdown
    print("🏷️  **Issues by Category:**")
    for category, count in issues['by_category'].items():
        category_name = category.replace('_', ' ').title()
        print(f"   • {category_name}: {count} issues")
    print()


def _print_analyzer_scores(metrics: dict) -> None:
    """
    Print individual analyzer scores with visual indicators.

    Issue #281: Extracted from run_comprehensive_quality_analysis to reduce
    function length and improve readability of dashboard output sections.
    """
    print("🔍 **Individual Analysis Scores:**")
    score_categories = [
        ('Security', metrics['security_score'], '🛡️'),
        ('Performance', metrics['performance_score'], '⚡'),
        ('Architecture', metrics['architecture_score'], '🏗️'),
        ('Test Coverage', metrics['test_coverage_score'], '🧪'),
        ('API Consistency', metrics['api_consistency_score'], '🔗'),
        ('Code Duplication', metrics['code_duplication_score'], '♻️'),
        ('Environment Config', metrics['environment_config_score'], '⚙️'),
    ]

    for name, score, emoji in score_categories:
        status = get_score_status(score)
        status_color = get_status_emoji(score)
        print(f"   {emoji} {name}: {score}/100 {status_color} {status}")
    print()


def _print_technical_debt(debt: dict) -> None:
    """
    Print technical debt analysis and effort breakdown.

    Issue #281: Extracted from run_comprehensive_quality_analysis to reduce
    function length and improve readability of dashboard output sections.
    """
    print("💸 **Technical Debt Analysis:**")
    print(f"   📊 Total Estimated Effort: {debt['estimated_total_effort_days']} days ({debt['estimated_total_effort_hours']} hours)")
    print(f"   🚨 Critical Issues Effort: {debt['estimated_critical_effort_hours']} hours")
    print(f"   📈 Debt Ratio: {debt['debt_ratio']}% of total project")
    print()

    print("💰 **Effort by Category:**")
    for category, data in debt['effort_by_category'].items():
        category_name = category.replace('_', ' ').title()
        print(f"   • {category_name}: {data['count']} issues, {data['effort_hours']} hours")
    print()


def _print_priority_issues(report: dict) -> None:
    """
    Print top priority issues requiring immediate action.

    Issue #281: Extracted from run_comprehensive_quality_analysis to reduce
    function length and improve readability of dashboard output sections.
    """
    print("🚨 **Top Priority Issues (Immediate Action Required):**")
    critical_issues = [issue for issue in report['prioritized_issues'] if issue['severity'] == 'critical']
    high_issues = [issue for issue in report['prioritized_issues'] if issue['severity'] == 'high']
    top_issues = critical_issues[:5] + high_issues[:5]

    for i, issue in enumerate(top_issues[:10], 1):
        severity_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
        emoji = severity_emoji.get(issue['severity'], "⚪")

        print(f"\n{i}. {emoji} **{issue['title']}** ({issue['severity'].upper()})")
        print(f"   📂 Category: {issue['category'].replace('_', ' ').title()}")
        if issue['file_path'] != 'Multiple files':
            print(f"   📄 File: {issue['file_path']}:{issue['line_number']}")
        print(f"   📝 Description: {issue['description']}")
        print(f"   💡 Fix: {issue['fix_suggestion']}")
        print(f"   🔧 Effort: {issue['estimated_effort'].title()}")
        print(f"   🎯 Priority Score: {issue['priority_score']}/100")
    print()


def _print_analysis_alerts(report: dict) -> None:
    """
    Print critical alerts for security, performance, and testing.

    Issue #281: Extracted from run_comprehensive_quality_analysis to reduce
    function length and improve readability of dashboard output sections.
    """
    # Security-specific analysis
    if report['detailed_analyses'].get('security'):
        security_data = report['detailed_analyses']['security']
        if security_data.get('critical_vulnerabilities', 0) > 0:
            print("🛡️ **CRITICAL SECURITY ALERT:**")
            print(f"   Found {security_data['critical_vulnerabilities']} critical security vulnerabilities!")
            print("   These must be addressed immediately before deployment.")
            print()

    # Performance-specific analysis
    if report['detailed_analyses'].get('performance'):
        perf_data = report['detailed_analyses']['performance']
        if perf_data.get('critical_issues', 0) > 0:
            print("⚡ **CRITICAL PERFORMANCE ALERT:**")
            print(f"   Found {perf_data['critical_issues']} critical performance issues!")
            print("   These may cause memory leaks or system instability.")
            print()

    # Testing coverage analysis
    if report['detailed_analyses'].get('testing_coverage'):
        test_data = report['detailed_analyses']['testing_coverage']
        coverage = test_data.get('test_coverage_percentage', 0)
        print(f"🧪 **Testing Coverage Analysis:**")
        print(f"   Current test coverage: {coverage}%")
        if coverage < 70:
            print("   ⚠️  Coverage is below recommended 70% threshold")
            print("   Consider adding more unit and integration tests")
        print()


async def run_comprehensive_quality_analysis():
    """Run comprehensive code quality analysis"""

    print("🎯 Starting comprehensive code quality analysis...")
    print("This will run all available analyzers:")
    print("  • Code Duplication Analyzer")
    print("  • Environment Variable Analyzer")
    print("  • Performance & Memory Leak Analyzer")
    print("  • Security Vulnerability Analyzer")
    print("  • API Consistency Analyzer")
    print("  • Testing Coverage Gap Analyzer")
    print("  • Architectural Pattern Analyzer")
    print()

    dashboard = CodeQualityDashboard()

    # Generate comprehensive report
    report = await dashboard.generate_comprehensive_report(
        root_path=".",
        patterns=["src/**/*.py", "backend/**/*.py"],
        include_trends=True
    )

    print("=== Code Quality Executive Summary ===\n")

    # Executive summary
    summary = await dashboard.generate_executive_summary(report)
    print(summary)

    print("\n=== Detailed Quality Analysis Results ===\n")

    # Issue #281: Use extracted helpers for dashboard sections
    metrics = report['quality_metrics']
    issues = report['issue_summary']
    debt = report['technical_debt']

    _print_executive_metrics(metrics, issues, report)
    _print_analyzer_scores(metrics)
    _print_technical_debt(debt)
    _print_priority_issues(report)
    _print_analysis_alerts(report)

    # Improvement recommendations
    print("📋 **Improvement Recommendations (Priority Order):**")
    for i, recommendation in enumerate(report['improvement_recommendations'], 1):
        print(f"{i}. {recommendation}")
    print()

    # Quality trends (if available)
    if report.get('quality_trends'):
        print("📈 **Quality Trends:**")
        trends = report['quality_trends']
        if len(trends) > 1:
            latest = trends[0]
            previous = trends[1]
            score_change = latest['overall_score'] - previous['overall_score']
            trend_emoji = "📈" if score_change > 0 else "📉" if score_change < 0 else "➡️"
            print(f"   {trend_emoji} Score change: {score_change:+.1f} points")

            issue_change = latest['issue_count'] - previous['issue_count']
            issue_emoji = "📉" if issue_change < 0 else "📈" if issue_change > 0 else "➡️"
            print(f"   {issue_emoji} Issue count change: {issue_change:+d}")
        else:
            print("   📊 Baseline measurement established")
        print()

    # Detailed analysis summaries
    print("📊 **Detailed Analysis Summaries:**")

    # Issue #315: Refactored with data-driven formatting instead of elif chain
    analysis_formats = {
        'duplication': {
            'name': 'Code Duplication', 'emoji': '♻️',
            'fields': [
                ('total_duplicate_groups', 'Found {} duplicate code groups'),
                ('total_lines_saved', 'Potential lines saved: {}'),
            ]
        },
        'environment': {
            'name': 'Environment Variables', 'emoji': '⚙️',
            'fields': [
                ('total_hardcoded_values', 'Found {} hardcoded values'),
                ('critical_hardcoded_values', 'Critical values: {}'),
            ]
        },
        'security': {
            'name': 'Security', 'emoji': '🛡️',
            'fields': [
                ('total_vulnerabilities', 'Found {} potential vulnerabilities'),
                ('critical_vulnerabilities', 'Critical vulnerabilities: {}'),
            ]
        },
        'performance': {
            'name': 'Performance', 'emoji': '⚡',
            'fields': [
                ('total_performance_issues', 'Found {} performance issues'),
                ('critical_issues', 'Critical issues: {}'),
            ]
        },
        'api_consistency': {
            'name': 'API Consistency', 'emoji': '🔗',
            'fields': [
                ('total_endpoints', 'Analyzed {} API endpoints'),
                ('inconsistencies_found', 'Found {} consistency issues'),
            ]
        },
        'testing_coverage': {
            'name': 'Testing Coverage', 'emoji': '🧪',
            'fields': [
                ('total_functions', 'Analyzed {} functions'),
                ('test_coverage_percentage', 'Test coverage: {}%'),
            ]
        },
        'architecture': {
            'name': 'Architecture', 'emoji': '🏗️',
            'fields': [
                ('total_components', 'Analyzed {} architectural components'),
                ('architectural_issues', 'Found {} architectural issues'),
            ]
        },
    }

    for analysis_type, fmt in analysis_formats.items():
        data = report['detailed_analyses'].get(analysis_type)
        if data:
            print(f"\n{fmt['emoji']} **{fmt['name']} Analysis:**")
            for field_key, field_fmt in fmt['fields']:
                value = data.get(field_key, 0)
                print(f"   • {field_fmt.format(value)}")

    # Save comprehensive report
    report_path = Path("comprehensive_quality_report.json")
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)

    # Generate summary report
    summary_path = Path("quality_summary.txt")
    with open(summary_path, 'w') as f:
        f.write(summary)

    print(f"\n=== Reports Generated ===")
    print(f"📋 Comprehensive report: {report_path}")
    print(f"📄 Executive summary: {summary_path}")

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

    print("\n=== 📋 Recommended Action Plan ===")

    metrics = report['quality_metrics']
    issues = report['issue_summary']

    # Phase 1: Critical Issues (Week 1)
    critical_count = issues['critical_issues']
    if critical_count > 0:
        print(f"\n🚨 **Phase 1: Critical Issues (IMMEDIATE - Week 1)**")
        print(f"   Address {critical_count} critical issues:")

        critical_issues = [i for i in report['prioritized_issues'] if i['severity'] == 'critical']
        for issue in critical_issues[:5]:  # Top 5 critical
            print(f"   • {issue['title']}")
            print(f"     Action: {issue['fix_suggestion']}")

    # Phase 2: High Priority (Weeks 2-3)
    high_count = issues['high_priority_issues']
    if high_count > 0:
        print(f"\n⚠️  **Phase 2: High Priority (Weeks 2-3)**")
        print(f"   Address {high_count} high priority issues:")

        if metrics['security_score'] < 80:
            print("   • Complete security vulnerability audit")
        if metrics['performance_score'] < 70:
            print("   • Fix performance bottlenecks and memory leaks")
        if metrics['test_coverage_score'] < 70:
            print("   • Increase test coverage to 80%+")

    # Phase 3: Quality Improvements (Month 2)
    print(f"\n🔧 **Phase 3: Quality Improvements (Month 2)**")
    if metrics['architecture_score'] < 80:
        print("   • Refactor architectural issues")
    if metrics['code_duplication_score'] < 80:
        print("   • Eliminate code duplication")
    if metrics['api_consistency_score'] < 80:
        print("   • Standardize API patterns")

    # Phase 4: Maintenance & Monitoring (Ongoing)
    print(f"\n📈 **Phase 4: Continuous Improvement (Ongoing)**")
    print("   • Set up automated quality monitoring")
    print("   • Implement pre-commit quality checks")
    print("   • Regular quality reviews (weekly)")
    print("   • Update team coding standards")

    # Estimated timeline
    debt = report['technical_debt']
    total_days = debt['estimated_total_effort_days']
    critical_hours = debt['estimated_critical_effort_hours']

    print(f"\n⏰ **Estimated Timeline:**")
    print(f"   • Critical fixes: {critical_hours} hours (1-2 weeks)")
    print(f"   • Total remediation: {total_days} days ({total_days/5:.1f} weeks)")
    print(f"   • Team of 2-3 developers recommended")


async def main():
    """Run comprehensive code quality analysis"""

    # Run analysis
    report = await run_comprehensive_quality_analysis()

    # Generate action plan
    await generate_action_plan(report)

    print("\n=== 🎯 Analysis Complete ===")
    print("Next Steps:")
    print("1. Review comprehensive_quality_report.json for detailed findings")
    print("2. Start with critical security and performance issues")
    print("3. Follow the recommended action plan phases")
    print("4. Set up automated quality monitoring")
    print("5. Schedule regular quality reviews")


if __name__ == "__main__":
    asyncio.run(main())
